"""Conflict check against the Promise Register (FR-27 - FR-32).

Structured matching in code on industry, geography, entity (incl. Affiliates),
services, rates and assets. Definitions travel with clauses: Al Noor's 'hotel'
and 'GCC' sit in §1.9/§1.11, not in §12. The phrase that would declare a deal
clear of past promises is never produced (GR-03); coverage is always stated.
"""

import re

from .checks import fid
from .knowledge import CLIENT_DIRECTORY, GCC, PLACES
from .register import INDUSTRY_WORDS
from .text import best_quote, read_dataset_file, sentences

SERVICE_WORDS = {
    "analytics": r"analytics|dashboard|business intelligence|\bBI\b",
    "ai": r"artificial intelligence|\bAI\b|machine learning|model|recommendation|ranking|sentiment|propensity|forecast",
    "revenue management": r"revenue management|rate recommendation|dynamic rate|pricing",
}


def _countries(text):
    found = set()
    for k, v in PLACES.items():
        if re.search(r"\b" + re.escape(k) + r"\b", text):
            found.add(v)
    return found


def profile(doc):
    """Read the deal's attributes out of the draft (what the register is matched against)."""
    clauses = doc["clauses"]
    atliq_rx = re.compile(r"AtliQ|ATLIQ|Baner|Pune 411045|Princeton|College Road")
    about = []   # what the counterparty is and does: parties, recitals, background, preamble
    for c in clauses:
        if re.search(r"part|recital|background|preamble", c["heading"], re.I) or re.search(r"WHEREAS|operates|owns", c["text"]):
            about.extend(s for s in sentences(c["text"]) if not atliq_rx.search(s))
    about_text = " ".join(about)
    scope_text = " ".join(c["text"] for c in clauses if re.search(r"scope|services|appointment|definitions|schedule|annex|exhibit|propert", c["heading"], re.I))
    full = doc["text"]
    primary = [k for k, rx in INDUSTRY_WORDS.items() if re.search(rx, about_text, re.I) and k != "hospitality"]
    if re.search(r"(owns|operates|manages|franchises)[^.]{0,60}\b(hotels|resorts|serviced apartments)", about_text, re.I):
        primary.append("hospitality")   # the counterparty *is* a hotel business, not just a booking app
    if doc["side"] == "partner" and re.search(INDUSTRY_WORDS["cloud data platform"], full, re.I):
        primary.append("cloud data platform")
    distribution = bool(re.search(r"Partner Hotel|hotel results|book hotels|listing and booking", full))
    hq = _countries(" ".join(s for s in about if re.search(r"incorporated|registered|office|head office|principal|licensed", s)))
    # property / territory tables
    props = set()
    prop_names = []
    for row in re.findall(r"^\|([^\n]+)\|\s*$", full, re.M):
        cells = [x.strip() for x in row.split("|")]
        if len(cells) >= 3 and any(re.search(r"\b" + re.escape(k) + r"\b", row) and v in GCC for k, v in PLACES.items()):
            prop_names.append(cells[1])
    for c in clauses:
        if re.search(r"propert|territory|schedule|annex", c["heading"] + " " + c.get("title", ""), re.I) or re.search(r"\"\*\*Territory\*\*\"", c["text"]):
            props |= _countries(c["text"])
    geos = _countries(scope_text) | props | hq
    if re.search(r"Gulf Cooperation Council|\bGCC\b", full):
        geos |= set(GCC)
    services = [k for k, rx in SERVICE_WORDS.items() if re.search(rx, scope_text or full)]
    rates = {}
    for m in re.finditer(r"^\|\s*([A-Za-z ]+?)\s*\|\s*\$(\d+(?:\.\d+)?)\s*\|", full, re.M):
        rates[m.group(1).strip()] = float(m.group(2))
    assets = sorted(set(re.findall(r"\bPipeKit\b", full)))
    warranty = None
    for c in clauses:
        for s in sentences(c["text"]):
            if re.search(r"not bound by any agreement or restriction", s):
                warranty = (c, s)
    return {"primary": primary, "distribution": distribution, "hq": sorted(hq), "properties": sorted(props), "gcc_property_names": prop_names,
            "geos": sorted(geos), "services": services, "rates": rates, "assets": assets, "warranty": warranty}


def _norm_role(r):
    return re.sub(r"[^a-z]", "", r.lower())


def check(doc, register, findings):
    prof = profile(doc)
    conflicts, history, sources = [], [], set()
    entity = doc.get("entity_named")
    by_parent = {}
    for e in register:
        if e.get("parent"):
            by_parent.setdefault(e["parent"], []).append(e)

    def add(e, certainty, severity, draft_ref, draft_quote, why, question=None, extra=None):
        src_text = read_dataset_file("signed_contracts/" + e["file"])
        sources.add("signed_contracts/" + e["file"])
        waivers = []
        for w in by_parent.get(e["id"], []):
            sources.add("signed_contracts/" + w["file"])
            covers = w.get("beneficiary", "").split()[0].lower() in doc["counterparty"].lower() if w.get("beneficiary") else False
            waivers.append({"id": w["id"], "file": w["file"], "status": w["status"], "covers_this_deal": covers,
                            "limits": w["activity"], "quote": w["anchors"][1] if len(w["anchors"]) > 1 else w["anchors"][0],
                            "verified": all(a["verified"] for a in w["anchor_checks"])})
        affiliate_note = ""
        if e.get("affiliates"):
            affiliate_note = "Binds AtliQ's Affiliates" + (" - AtliQ Inc (100% owned by Pvt Ltd) is caught" if "Pvt" in e["entity"] else " - AtliQ Pvt Ltd is caught")
        conflicts.append({
            "id": fid(doc["file"], e["id"]), "certainty": certainty, "severity": severity, "entry_id": e["id"],
            "entry_type": e["type"], "counterparty": e["counterparty"], "register_file": e["file"], "register_clauses": e["clauses"],
            "register_quote": e["anchors"][0], "register_quotes": [a for a in e["anchor_checks"]],
            "register_verified": e.get("verified", False), "draft_ref": draft_ref, "draft_quote": draft_quote,
            "entity_bound": e["entity"], "affiliates": affiliate_note, "end": e.get("end"), "end_note": e.get("end_note"),
            "status": e["status"], "waivers": waivers, "why": why, "question": question, "label": e.get("label"),
            "extra": extra or {}, "source_verified": all(a["verified"] for a in e["anchor_checks"]) and bool(src_text)})

    for e in register:
        if not e.get("confirmed"):
            continue
        t = e["type"]
        entity_caught = e.get("affiliates") or (("Inc" in e["entity"]) == (entity == "Inc"))
        if t == "Non-compete":
            ind_hit = any(i in prof["primary"] for i in e["industries"]) or ("hospitality" in e["industries"] and prof["distribution"])
            geo_hit = bool(set(e["geographies"]) & set(prof["geos"])) or "*" in e["geographies"]
            svc_hit = bool(set(e["services"]) & set(prof["services"])) or not e["services"]
            if not ind_hit or not entity_caught:
                continue
            if e["status"] == "expired":
                history.append({"entry_id": e["id"], "counterparty": e["counterparty"], "type": t, "end": e["end"],
                                "note": f"Expired {e['end']} ({e['activity']}; geography: {', '.join(e['geographies'])}). Shown for history only."})
                continue
            if not (geo_hit and svc_hit):
                continue
            gcc_hq = bool(set(prof["hq"]) & set(e["geographies"]))
            direct = "hospitality" in prof["primary"] and gcc_hq
            draft_c = next((c for c in doc["clauses"] if re.search(r"hotel|resort|Propert", c["text"], re.I) and re.search(r"analytic|revenue|AI|ranking|platform|sentiment", c["text"], re.I)), doc["clauses"][0])
            dq = best_quote(draft_c["text"], r"revenue management|guest analytics|analytics|ranking|Partner Hotels|hotel")
            if direct:
                q = None
                why = (f"{doc['counterparty']} is a Hospitality Business headquartered in the GCC ({', '.join(prof['hq'])}) and the draft buys "
                       f"{', '.join(prof['services'])} services - exactly what {e['clauses'].split(' ')[0]} forbids until {e['end']}.")
                cert = "Conflict"
            elif prof["distribution"] and "hospitality" not in prof["primary"]:
                gcc = sorted(set(prof["geos"]) & set(e["geographies"]))
                q = f"Is {doc['counterparty']} a distribution provider to GCC hotels - a 'Hospitality Business' under Al Noor §1.11 - given the module ranks hotels in {', '.join(gcc)}?"
                why = f"The draft builds a hotel ranking and booking module for properties in {', '.join(gcc)}. Al Noor §1.11 counts providers of distribution services to hotels as a Hospitality Business."
                cert = "Possible - confirm"
            else:
                gcc_props = sorted(set(prof["properties"]) & set(e["geographies"]))
                names = ", ".join(prof["gcc_property_names"]) or ", ".join(gcc_props)
                q = f"Are the GCC properties ({names}) in the pilot scope? Al Noor §12.2 catches services that relate to properties located in the GCC, wherever the client is headquartered."
                why = f"{doc['counterparty']} is headquartered outside the GCC, but its property schedule lists {len(prof['gcc_property_names']) or len(gcc_props)} GCC properties ({names}). The Seaside waiver does not extend to other hotels."
                cert = "Possible - confirm"
            add(e, cert, "Serious", draft_c["ref"], dq, why, q)
            if prof["warranty"]:
                wc, ws = prof["warranty"]
                findings.append({"id": fid(doc["file"], "warranty", e["id"]), "key": "warranty", "severity": "Serious", "principle": "P9",
                                 "title": "Warranty that AtliQ is bound by no restriction",
                                 "reason": f"AtliQ would warrant it is not bound by any restriction, while {e['counterparty']} {e['clauses'].split(' (')[0]} is active until {e['end']}. Signing as drafted would make the warranty untrue on day one.",
                                 "clause_ref": wc["ref"], "clause_title": wc.get("title"), "quote": ws, "exposure": None,
                                 "category": "Conflict", "precedents": [], "origin": "rule", "definitions": []})
        elif t == "Most-favoured pricing" and prof["rates"] and e.get("rates") and entity_caught and e["status"] == "active":
            lower = []
            for role, r in prof["rates"].items():
                for erole, er in e["rates"].items():
                    if _norm_role(role) == _norm_role(erole) and r < er:
                        lower.append({"role": role, "draft": r, "register": er, "gap": er - r})
            if lower:
                rc = next(c for c in doc["clauses"] if re.search(r"\|\s*\$", c["text"]))
                why = "Draft rates are below the rates promised to " + e["counterparty"] + ": " + "; ".join(
                    f"{l['role']} ${l['draft']:g} vs ${l['register']:g}" for l in lower) + \
                      ". Lower rates would apply to Crestline retroactively, with credits and audit rights."
                extra = {"rate_table": lower}
                if doc.get("informal") == "yes" and doc.get("informal_note"):
                    extra["informal_note"] = doc["informal_note"]
                add(e, "Conflict", "Serious", rc["ref"], best_quote(rc["text"], r"\$"), why,
                    "Are these 'substantially similar services' to Crestline's (data engineering and BI)?", extra)
        elif t == "Exclusivity" and doc["side"] == "partner" and "cloud data platform" in prof["primary"] and e["status"] == "active":
            overlap = sorted(set(e["geographies"]) & set(prof["geos"]))
            if overlap and entity_caught:
                tc = next((c for c in doc["clauses"] if "Territory" in c["text"] and "means" in c["text"]), doc["clauses"][0])
                add(e, "Conflict", "Serious", tc["ref"],
                    best_quote(tc["text"], r"Territory"),
                    f"Appointment as implementation partner for a competing lakehouse platform in a territory that includes {', '.join(['India'] if 'India' in overlap else [])}{' and the GCC' if set(overlap) & set(GCC) else ''}. CloudSpan's exclusivity binds AtliQ and its Affiliates until {e['end']}.",
                    None, {"termination": "CloudSpan §14.2 allows either party 90 days' termination for convenience."})
        elif t == "IP assignment" and e.get("assets") and set(e["assets"]) & set(prof["assets"]):
            ac = next((c for c in doc["clauses"] if re.search(r"sole owner", c["text"])), None) or next(c for c in doc["clauses"] if "PipeKit" in c["text"])
            add(e, "Conflict", "Serious", ac["ref"], best_quote(ac["text"], r"sole owner|PipeKit"),
                f"{e['counterparty']} {e['clauses']} assigned IP in pre-existing materials incorporated in its deliverables, and its SOW incorporated PipeKit. AtliQ may no longer own what this draft warrants and licenses.",
                "Who owns PipeKit after the Northwind assignment? (legal question - counsel)")
        elif t == "Capacity commitment" and re.search(r"Certified Engineers", doc["text"]) and doc["side"] == "partner":
            cc = next(c for c in doc["clauses"] if "Certified Engineers" in c["text"])
            add(e, "Possible - confirm", "Review", cc["ref"], best_quote(cc["text"], r"Certified"),
                f"This draft adds a certification headcount commitment on top of the {e['counterparty']} commitment (4 certified engineers).",
                "Does AtliQ have enough certified engineers to meet both commitments at once?")

    # reverse conflicts: a new covenant in the draft that would bite existing clients
    for f in findings:
        if f.get("key") == "new-restriction":
            quote = f["quote"]
            c = next((c for c in doc["clauses"] if c["ref"] == f["clause_ref"]), None)
            context = quote + " " + " ".join(cl["text"] for cl in doc["clauses"] if "Competitor" in cl["text"] and "means" in cl["text"])
            inds = [k for k, rx in INDUSTRY_WORDS.items() if re.search(rx, context, re.I)]
            hits = [cl for cl in CLIENT_DIRECTORY if cl["industry"] in inds and cl["country"] in _countries(context) | {"India"}]
            if hits:
                sources.add("contract_tracker.csv")
                for h in hits:
                    sources.add(h["source"])
                conflicts.append({
                    "id": fid(doc["file"], "reverse", f["clause_ref"]), "certainty": "Conflict", "severity": "Serious",
                    "entry_id": "CLIENTS", "entry_type": "Existing clients", "counterparty": ", ".join(h["name"] for h in hits),
                    "register_file": None, "register_clauses": "-", "register_quote": "; ".join(f"{h['name']}: {h['status']}" for h in hits),
                    "register_quotes": [], "register_verified": True, "draft_ref": f["clause_ref"], "draft_quote": quote,
                    "entity_bound": "AtliQ Technologies Pvt Ltd", "affiliates": "", "end": None, "end_note": "", "status": "active",
                    "waivers": [], "why": "The new covenant would restrict AtliQ from serving businesses it already serves or is negotiating with: " +
                    "; ".join(f"{h['name']} ({h['status']})" for h in hits) + ".",
                    "question": "Would the work for these clients count as 'similar services' to a 'Competitor'?",
                    "label": None, "extra": {"clients": hits}, "source_verified": True})
    return conflicts, history, prof, sources
