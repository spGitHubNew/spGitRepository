"""Review orchestration (PRD 7.3 / 9.3): segment -> rules + checks -> register match -> verify quotes -> assemble Serious-first."""

import hashlib
import json
import re
import time
from datetime import date

from . import conflicts as conflict_mod
from . import llm, store
from .checks import ALL_CHECKS, Ctx, check_unreadable, fid
from .knowledge import (BANNED_PHRASES, DEALS, DISCLAIMER, EVENTS, INTAKE, PRINCIPLES, PRINCIPLES_VERSION,
                        SEVERITY_ORDER, TODAY)
from .register import build_register, coverage, tracker_rows
from .rules import check_bundle, check_entity
from .text import (DATASET, attach_definitions, definitions, doc_title, norm, ocr_quality, parties, provenance,
                   read_dataset_file, segment, trim, verify_quote)

CHECKS_RUN = [
    "Every clause segmented and read; definitions attached to the clauses that use them",
    "Delay damages / penalties (P1) with exposure computed in code",
    "Liability caps and unlimited liability (P2)",
    "Indemnity scope, incl. the other side's negligence (P3)",
    "Payment days, pay-when-paid, set-off (P4)",
    "Signing entity, governing law, forum and invoicing entity vs finance's entity sheet (P5)",
    "IP in deliverables and pre-existing tools (P6)",
    "Termination and payment for work done (P7)",
    "NDA mutuality, residuals, hidden non-competes (P8)",
    "Promise Register conflict check incl. Affiliates and waivers (P9)",
    "AtliQ's own paper vs AtliQ's supplier-side positions (P10)",
    "Deal bundle, required documents and flow-downs (P11)",
    "Requirements vs AtliQ facts table (insurance, headcount)",
    "Missing annexes, prevailing other-language texts, instruction-like text",
]

_cache = {}


def _slug(file):
    return re.sub(r"\.md$|\.txt$", "", file.split("/")[-1])


def _doc_from(file_rel, text, meta, kind):
    clauses = segment(text)
    defs = definitions(clauses)
    attach_definitions(clauses, defs)
    p = parties(text)
    cp = meta.get("counterparty") or p.get("other_name") or "Counterparty"
    labels = {"atliq": p["atliq"], "other": list(p["other"])}
    first = re.split(r"[\s,]+", cp)[0]
    if first and first not in labels["other"] and first.lower() != "atliq":
        labels["other"].append(first)
    doc = {"id": meta.get("id") or _slug(file_rel), "file": file_rel, "kind": kind, "text": text,
           "title": doc_title(text), "provenance": provenance(text), "clauses": clauses, "definitions": defs,
           "labels": labels, "entity_named": p["atliq_entity"], "counterparty": cp,
           "doc_type": meta.get("doc_type") or doc_title(text), "side": meta.get("side") or "supplier",
           "service_region": meta.get("service_region") or "", "value": meta.get("value"),
           "currency": meta.get("currency") or "USD", "deadline": meta.get("deadline"), "seller": meta.get("seller"),
           "deal": meta.get("deal"), "tracker_id": meta.get("tracker_id"), "informal": meta.get("informal", "no"),
           "informal_note": meta.get("informal_note", ""), "received": meta.get("received"), "ocr": ocr_quality(text)}
    return doc


def corpus():
    state = store.load()
    key = hashlib.sha1(json.dumps([state.get("uploads"), state.get("intake_overrides")], sort_keys=True).encode()).hexdigest()
    if _cache.get("corpus_key") == key:
        return _cache["corpus"]
    rows = {r["contract_id"]: r for r in tracker_rows()}
    docs = {}
    for f, meta in INTAKE.items():
        meta = dict(meta, **state["intake_overrides"].get(_slug(f), {}))
        meta["received"] = rows.get(meta["tracker_id"], {}).get("received_date") or None
        docs[_slug(f)] = _doc_from("incoming/" + f, read_dataset_file("incoming/" + f), meta, "incoming")
    for p in sorted((DATASET / "signed_contracts").glob("*.md")):
        d = _doc_from("signed_contracts/" + p.name, p.read_text(encoding="utf-8"), {"side": "supplier"}, "signed")
        docs[d["id"]] = d
    for uid, up in state["uploads"].items():
        path = store.UPLOADS / up["stored"]
        if path.exists():
            docs[uid] = _doc_from("uploads/" + up["stored"], path.read_text(encoding="utf-8"), dict(up["meta"], id=uid), "upload")
    _cache.clear()
    _cache.update(corpus_key=key, corpus=docs)
    return docs


def register_entries():
    return build_register(store.load()["register"])


# ------------------------------------------------------------------ guardrails

def guard(obj, hits):
    """GR-03: banned phrases are never output. Replace and record."""
    if isinstance(obj, str):
        out = obj
        for p in BANNED_PHRASES:
            if p in out.lower():
                hits.append(p)
                out = re.sub(re.escape(p), "[phrase withheld by guardrail]", out, flags=re.I)
        return out
    if isinstance(obj, list):
        return [guard(x, hits) for x in obj]
    if isinstance(obj, dict):
        return {k: guard(v, hits) for k, v in obj.items()}
    return obj


def _fair_table(ctx, doc):
    order = ["Liability", "Indemnity", "Delay damages", "Payment", "Termination for convenience",
             "Confidentiality obligations", "Restrictive covenants", "Non-solicit"]
    groups = {}
    for typ, side, s, ref in ctx.fair:
        g = groups.setdefault(typ, {"type": typ, "atliq": [], "other": [], "both": []})
        item = {"ref": ref, "text": trim(s, 240)}
        if item not in g[side if side in g else "both"]:
            g[side if side in g else "both"].append(item)
    rows = []
    for typ in order:
        if typ in groups:
            g = groups[typ]
            g["asymmetric"] = bool(g["atliq"]) != bool(g["other"]) or (typ == "Liability" and bool(g["atliq"]) and bool(g["other"]) and any(
                re.search(r"NOTHING|not be subject|without limitation", x["text"], re.I) for x in g["atliq"] + g["other"]))
            rows.append(g)
    return rows


def run_review(doc_id, use_ai=False):
    t0 = time.perf_counter()
    docs = corpus()
    doc = docs[doc_id]
    register = register_entries()
    ctx = Ctx(doc)
    deal = DEALS.get(doc.get("deal")) if doc.get("deal") else None
    bundle_docs = [d for d in docs.values() if d.get("deal") == doc.get("deal") and d["kind"] != "signed"] if deal else [doc]
    for check in ALL_CHECKS:
        check(ctx)
    check_unreadable(ctx, [d["title"] for d in bundle_docs if d is not doc])
    entity_rows = check_entity(ctx)

    bundle = None
    if deal:
        signed_members = [docs[_slug(f)] for f in deal["signed_members"]]
        related = [docs[_slug(f)] for f in deal["related_signed"]]
        bundle = check_bundle(doc["deal"], deal, bundle_docs, signed_members, related)
        counts = "nda" not in doc["doc_type"].lower()
        bundle["counts_toward_summary"] = counts
        for i in bundle["issues"]:
            src = docs[_slug(i["source_file"])]["text"] if i.get("source_file") else ""
            i["verified"] = verify_quote(i["quote"], src)
        if counts:
            ctx.findings.extend(dict(i, id=fid(doc["file"], i["id"])) for i in bundle["issues"]
                                if not (i["key"] == "staffing-entity" and i.get("source_file") == doc["file"]))

    conflicts, history, prof, conflict_sources = conflict_mod.check(doc, register, ctx.findings)

    ai_note = None
    if use_ai and llm.available():
        extra, ai_note = llm.second_pass(doc, ctx.findings, PRINCIPLES)
        for f in extra:
            ctx.findings.append({"id": fid(doc["file"], "ai", f["clause_ref"], f["title"]), "key": "ai", "severity": f["severity"],
                                 "principle": f["principle"], "title": f["title"], "reason": f["reason"], "clause_ref": f["clause_ref"],
                                 "clause_title": "", "quote": f["quote"], "exposure": None, "category": "AI second pass",
                                 "precedents": [], "origin": "ai", "definitions": []})
        for c in conflicts:
            if c["certainty"].startswith("Possible"):
                c["ai_explanation"] = llm.explain_conflict(c)
    elif use_ai:
        ai_note = "AI second pass not configured (set COUNTERSIGN_AI=1 and Anthropic credentials). Rule-based review is complete on its own."

    # GR-02: verify every quote
    seen, findings = set(), []
    for f in ctx.findings:
        if f["id"] in seen:
            continue
        seen.add(f["id"])
        if "verified" not in f:
            f["verified"] = verify_quote(f["quote"], doc["text"])
        if not f["verified"]:
            f["display_status"] = "Not sure - please cross-check"
        findings.append(f)
    for c in conflicts:
        c["draft_verified"] = verify_quote(c["draft_quote"] or "", doc["text"])
    def natural(ref):
        nums = [int(n) for n in re.findall(r"\d+", ref)]
        return nums or [9999]
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["category"] == "Bundle & flow-down", natural(f["clause_ref"])))

    sev = {"Serious": 0, "Review": 0, "Minor": 0}
    for f in findings:
        sev[f["severity"]] += 1
    serious_conflicts = sum(1 for c in conflicts if c["severity"] == "Serious")
    cov = coverage(register)
    ld = next((f for f in findings if f["key"] == "ld" and f.get("exposure")), None)
    liab = next((f for f in findings if f["key"] == "liab-unlimited"), None)
    elapsed = time.perf_counter() - t0

    events = [e for e in EVENTS if deal and e["deal"] == doc.get("deal") or e["deal"] == ("gulfcrown" if "gulf_crown" in doc["file"] else None)]
    for e in events:
        for s in e["sources"]:
            s["verified"] = verify_quote(s["quote"], read_dataset_file(s["file"]))

    sources = {doc["file"], "atliq_entities.md", "karandeep_contract_checklist.md"} | conflict_sources
    if bundle:
        sources |= {d["file"] for d in bundle_docs} | {"signed_contracts/" + f for f in deal["signed_members"] + deal["related_signed"]}
    if any(f.get("precedents") for f in findings):
        sources.add("negotiation_notes.md")
    for e in events:
        sources |= {s["file"] for s in e["sources"]}
    if any(f["key"].startswith("insurance") for f in findings):
        sources.add("meeting_notes/2026-09-27_harrington_huddle.md")

    clean = sev["Serious"] == 0 and serious_conflicts == 0
    review = {
        "doc": {k: doc[k] for k in ("id", "file", "kind", "title", "provenance", "counterparty", "doc_type", "side",
                                    "service_region", "value", "currency", "deadline", "seller", "deal", "tracker_id",
                                    "entity_named", "informal", "informal_note", "received", "ocr")},
        "review_line": {"clauses_total": len(doc["clauses"]), "clauses_reviewed": len(doc["clauses"]),
                        "elapsed_seconds": round(elapsed, 2), "deadline": doc.get("deadline"),
                        "entity_named": doc.get("entity_named"), "definitions": len(doc["definitions"])},
        "coverage": cov,
        "summary": {"serious": sev["Serious"] + serious_conflicts, "review": sev["Review"] + sum(1 for c in conflicts if c["severity"] == "Review"),
                    "minor": sev["Minor"], "conflicts": len(conflicts), "value": doc.get("value"), "currency": doc.get("currency"),
                    "ld_exposure": ld["exposure"] if ld else None, "liability": "unlimited" if liab else None},
        "findings": findings, "conflicts": conflicts, "history": history, "profile": {k: v for k, v in prof.items() if k != "warranty"},
        "fairness": _fair_table(ctx, doc), "entity": entity_rows, "bundle": bundle,
        "could_not_check": ctx.could_not_check + ([f"Low-confidence scan: {doc['ocr']['illegible']} illegible passage(s); extracted entries need human review."] if doc["ocr"]["low_confidence"] else []),
        "checks_run": CHECKS_RUN, "checks_passed": ctx.passed, "actions_now": events,
        "clean_message": ("No Serious findings from the checks we ran (listed below). This is not a clearance." if clean else None),
        "sources_consulted": sorted(sources), "principles_version": PRINCIPLES_VERSION, "ai_note": ai_note,
        "disclaimer": DISCLAIMER,
    }
    hits = []
    review = guard(review, hits)
    if hits:
        store.audit("guardrail_triggered", "system", doc_id=doc_id, phrases=hits)
    return review


def get_review(doc_id, use_ai=False):
    state = store.load()
    key = (doc_id, use_ai, json.dumps(state["register"], sort_keys=True), json.dumps(state["intake_overrides"].get(doc_id, {})))
    if key not in _cache:
        r = run_review(doc_id, use_ai)
        _cache[key] = r
        st = state["status"].setdefault(doc_id, {})
        if not st.get("review_ready"):
            st["review_ready"] = store.now()
            st.setdefault("stage", "Review ready")
            store.save(state)
            store.audit("review_ready", "system", doc_id=doc_id, serious=r["summary"]["serious"],
                        findings=len(r["findings"]), conflicts=len(r["conflicts"]),
                        quotes_verified=sum(1 for f in r["findings"] if f["verified"]), quotes_total=len(r["findings"]))
    return _cache[key]


def invalidate():
    for k in list(_cache):
        if isinstance(k, tuple):
            del _cache[k]


# ------------------------------------------------------------------ decisions and status

def open_items(review, decisions):
    items = [f for f in review["findings"] if f["severity"] == "Serious"] + review["conflicts"]
    return [i for i in items if i["id"] not in decisions]


def status_card(doc_id):
    state = store.load()
    r = get_review(doc_id)
    d = state["decisions"].get(doc_id, {})
    st = state["status"].get(doc_id, {})
    rec = r["doc"].get("received")
    waiting = (TODAY - date.fromisoformat(rec)).days if rec else None
    missing = [x["doc"] for x in (r["bundle"] or {}).get("documents", []) if x["status"].startswith("Missing")]
    return {"id": doc_id, "counterparty": r["doc"]["counterparty"], "doc_type": r["doc"]["doc_type"], "seller": r["doc"]["seller"],
            "deadline": r["doc"]["deadline"], "received": rec, "days_waiting": waiting, "value": r["doc"]["value"],
            "currency": r["doc"]["currency"], "side": r["doc"]["side"], "stage": st.get("stage", "Received"),
            "serious": r["summary"]["serious"], "review": r["summary"]["review"], "minor": r["summary"]["minor"],
            "conflicts": r["summary"]["conflicts"], "open_serious": len(open_items(r, d)), "documents_missing": missing,
            "kind": r["doc"]["kind"], "clean": bool(r["clean_message"]), "actions_now": len(r["actions_now"]),
            "entity": r["doc"]["entity_named"]}


def queue():
    docs = corpus()
    return [status_card(i) for i, d in docs.items() if d["kind"] in ("incoming", "upload")]


def gate(doc_id):
    state = store.load()
    r = get_review(doc_id)
    open_ = open_items(r, state["decisions"].get(doc_id, {}))
    return {"ready_enabled": not open_, "open": [{"id": i["id"], "title": i.get("title") or (i.get("certainty", "") + " - " + i.get("counterparty", ""))} for i in open_]}


def refuse_or_answer(question, doc_id=None):
    if re.search(r"safe to sign|is (it|this) (safe|ok|okay|fine|enforceable|legal)|enforceab|legal advice|should (i|we) sign|can (i|we) sign|is this legal|will (this|it) hold up", question, re.I):
        return {"refused": True, "answer": "I can't give legal advice, judge enforceability or tell you whether to sign - a person decides. "
                "I can prepare a counsel pack (draft, open findings, related register entries and source files) for you to send to Mehta Rao or Calloway Stern.",
                "offer": "counsel_pack"}
    # grounded lookup: findings and register entries matching the question words
    words = [w for w in re.findall(r"[a-zA-Z]{4,}", question.lower()) if w not in {"what", "which", "does", "have", "with", "this", "that", "there", "about", "from", "into", "they", "will"}]
    hits = []
    if doc_id:
        r = get_review(doc_id)
        for f in r["findings"]:
            blob = (f["title"] + " " + f["reason"] + " " + f["quote"]).lower()
            score = sum(1 for w in words if w in blob)
            if score:
                hits.append((score, {"kind": "finding", "ref": f["clause_ref"], "title": f["title"], "quote": f["quote"], "severity": f["severity"]}))
    for e in register_entries():
        blob = (e["counterparty"] + " " + e["type"] + " " + e["activity"] + " " + " ".join(e.get("geographies", []))).lower()
        score = sum(1 for w in words if w in blob)
        if score:
            hits.append((score, {"kind": "register", "ref": f"{e['counterparty']} {e['clauses']}", "title": e["type"], "quote": e["anchors"][0],
                                 "severity": e["status"]}))
    hits.sort(key=lambda x: -x[0])
    out = guard({"refused": False, "answer": "Matching items with their source text:" if hits else
                 "Nothing in this review or the register matched those words. Try the register search with an industry and country.",
                 "results": [h for _, h in hits[:6]]}, [])
    return out


def counsel_pack(doc_id, user):
    import html
    state = store.load()
    r = get_review(doc_id)
    d = state["decisions"].get(doc_id, {})
    docs = corpus()
    open_f = [f for f in r["findings"] if f["id"] not in d or d[f["id"]]["disposition"] == "needs counsel"]
    files = {"signed_contracts/" + c["register_file"] for c in r["conflicts"] if c.get("register_file")}
    for c in r["conflicts"]:
        for w in c["waivers"]:
            files.add("signed_contracts/" + w["file"])
    if r["bundle"]:
        files |= {x["file"] for x in r["bundle"]["documents"] if x.get("file")}
    e = html.escape
    parts = [f"<!doctype html><meta charset='utf-8'><title>Counsel pack - {e(r['doc']['counterparty'])}</title>",
             "<style>body{font:14px/1.5 Georgia,serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#222}h1,h2{font-family:system-ui}"
             "blockquote{border-left:3px solid #999;margin:.5rem 0;padding:.2rem .8rem;background:#f6f6f6}pre{white-space:pre-wrap;background:#fafafa;border:1px solid #ddd;padding:1rem;font-size:12px}"
             ".sev{font-weight:bold}</style>",
             f"<h1>Counsel pack - {e(r['doc']['counterparty'])} ({e(r['doc']['doc_type'])})</h1>",
             f"<p><b>{e(DISCLAIMER)}</b> Prepared by CounterSign for {e(user)} on {store.now()}. CounterSign sends nothing; a person sends this pack.</p>",
             f"<p>{e(r['coverage']['line'])}</p><h2>Open findings ({len(open_f)})</h2>"]
    for f in open_f:
        parts.append(f"<p class='sev'>{e(f['severity'])} - {e(f['title'])} ({e(f['clause_ref'])}, {e(f['principle'])})</p><p>{e(f['reason'])}</p><blockquote>{e(f['quote'])}</blockquote>")
    parts.append(f"<h2>Possible collisions with signed contracts ({len(r['conflicts'])})</h2>")
    for c in r["conflicts"]:
        parts.append(f"<p class='sev'>{e(c['certainty'])} - {e(c['counterparty'])} {e(c['register_clauses'])}</p><p>{e(c['why'])}</p>"
                     f"<blockquote>Signed: {e(c['register_quote'])}</blockquote><blockquote>Draft {e(c['draft_ref'] or '')}: {e(c['draft_quote'] or '')}</blockquote>"
                     + (f"<p><i>Question that settles it: {e(c['question'])}</i></p>" if c.get("question") else ""))
    parts.append("<h2>Source documents</h2>")
    for f in [r["doc"]["file"]] + sorted(files - {r["doc"]["file"]}):
        try:
            txt = read_dataset_file(f)
        except OSError:
            continue
        parts.append(f"<h3>{e(f)}</h3><pre>{e(txt)}</pre>")
    store.audit("counsel_pack_prepared", user, doc_id=doc_id, findings=len(open_f), files=len(files) + 1)
    return "".join(parts)
