"""CounterSign - AtliQ Contract Risk Analyzer. Zero-dependency web server (Python standard library).

    python app.py            -> http://localhost:8765

Prototype on the synthetic dataset. Role switching stands in for SSO/RBAC (PRD 8);
the system never signs, approves, sends or negotiates anything (GR-01).
"""

import base64
import hashlib
import json
import mimetypes
import os
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import llm, review as R, store  # noqa: E402
from engine.ingest import extract_text, phi_scan  # noqa: E402
from engine.knowledge import (DEALS, DISCLAIMER, FACTS, PRINCIPLES, PRINCIPLES_VERSION, TODAY)  # noqa: E402
from engine.register import coverage, extract_promises  # noqa: E402

STATIC = ROOT / "static"
PORT = int(os.environ.get("PORT", "8765"))

USERS = {
    "Karandeep": {"role": "reviewer", "title": "CEO - reviewer and signatory"},
    "Bhavin": {"role": "seller", "title": "Founder - seller"},
    "Dhaval": {"role": "seller", "title": "Founder - seller"},
    "Jay": {"role": "seller", "title": "Sales - seller and register custodian", "custodian": True},
    "Pranav": {"role": "cto", "title": "CTO - author of AtliQ paper"},
}
DISPOSITIONS = {"accept", "negotiate", "needs counsel", "reject"}


class Forbidden(Exception):
    pass


def can_view_review(user, doc):
    u = USERS[user]
    if u["role"] == "reviewer":
        return True
    if u["role"] == "cto":
        return doc.get("seller") == user or doc.get("side") == "buyer"
    return doc.get("seller") == user


class Handler(BaseHTTPRequestHandler):
    server_version = "CounterSign/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    # ------------------------------------------------------------ plumbing
    def user(self):
        u = self.headers.get("X-User", "Karandeep")
        return u if u in USERS else "Karandeep"

    def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else (json.dumps(body) if not isinstance(body, str) else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method):
        url = urlparse(self.path)
        path, qs = url.path, {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if method == "GET" and (path == "/" or path.startswith("/static/")):
                return self.static(path)
            handler = getattr(self, "api_" + method.lower() + "_" + re.sub(r"^/api/|/.*$", "", path).replace("-", "_"), None)
            if not path.startswith("/api/") or handler is None:
                return self.send(404, {"error": "not found"})
            arg = path.split("/", 3)[3] if path.count("/") >= 3 else None
            return handler(arg, qs)
        except Forbidden as e:
            return self.send(403, {"error": str(e)})
        except KeyError as e:
            return self.send(404, {"error": f"unknown item {e}"})
        except ValueError as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:  # never fail silently (PRD 8 reliability)
            traceback.print_exc()
            return self.send(500, {"error": f"{type(e).__name__}: {e}"})

    def static(self, path):
        f = STATIC / ("index.html" if path == "/" else path[len("/static/"):])
        if not f.resolve().is_relative_to(STATIC.resolve()) or not f.exists():
            return self.send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        return self.send(200, f.read_bytes(), ctype)

    # ------------------------------------------------------------ meta
    def api_get_meta(self, _, qs):
        return self.send(200, {"today": TODAY.isoformat(), "users": USERS, "principles": PRINCIPLES,
                               "principles_version": PRINCIPLES_VERSION, "disclaimer": DISCLAIMER,
                               "ai_available": llm.available(), "ai_model": llm.MODEL, "facts": FACTS,
                               "deals": {k: v["name"] for k, v in DEALS.items()}})

    # ------------------------------------------------------------ queue and review
    def api_get_queue(self, _, qs):
        user = self.user()
        cards = R.queue()
        if USERS[user]["role"] == "seller":
            cards = [c for c in cards if c["seller"] == user] if qs.get("scope") != "all" else cards
        for c in cards:
            c["can_open"] = can_view_review(user, R.corpus()[c["id"]])
        return self.send(200, {"cards": cards, "coverage": coverage(R.register_entries())})

    def api_get_review(self, doc_id, qs):
        user = self.user()
        docs = R.corpus()
        doc = docs[doc_id]
        if not can_view_review(user, doc):
            raise Forbidden(f"{user} can see the status card for this contract, not the full review")
        r = R.get_review(doc_id, use_ai=qs.get("ai") == "1")
        state = store.load()
        st = state["status"].setdefault(doc_id, {})
        if user == "Karandeep" and not st.get("first_opened"):
            st["first_opened"] = store.now()
            store.save(state)
            store.audit("first_opened", user, doc_id=doc_id)
        store.audit("review_viewed", user, doc_id=doc_id, findings_shown=len(r["findings"]), conflicts_shown=len(r["conflicts"]))
        return self.send(200, {"review": r, "decisions": state["decisions"].get(doc_id, {}), "status": st,
                               "gate": R.gate(doc_id), "feedback": state["feedback"].get(doc_id),
                               "card": R.status_card(doc_id), "can_decide": USERS[user]["role"] == "reviewer"})

    def api_get_doc(self, doc_id, qs):
        doc = R.corpus()[doc_id]
        if not can_view_review(self.user(), doc) and doc["kind"] != "signed":
            raise Forbidden("not permitted")
        return self.send(200, {"id": doc_id, "file": doc["file"], "title": doc["title"], "text": doc["text"],
                               "clauses": [{"ref": c["ref"], "title": c["title"], "heading": c["heading"], "text": c["text"]} for c in doc["clauses"]]})

    def api_post_decision(self, _, qs):
        user = self.user()
        if USERS[user]["role"] != "reviewer":
            raise Forbidden("Only Karandeep records dispositions")
        b = self.body()
        doc_id, item_id, disp, reason = b["doc_id"], b["item_id"], b.get("disposition"), (b.get("reason") or "").strip()
        r = R.get_review(doc_id)
        item = next((f for f in r["findings"] + r["conflicts"] if f["id"] == item_id), None)
        if not item:
            raise KeyError(item_id)
        state = store.load()
        decisions = state["decisions"].setdefault(doc_id, {})
        if disp is None:
            decisions.pop(item_id, None)
            store.save(state)
            store.audit("disposition_cleared", user, doc_id=doc_id, item_id=item_id)
            return self.send(200, {"decisions": decisions, "gate": R.gate(doc_id)})
        if disp not in DISPOSITIONS:
            raise ValueError("disposition must be accept, negotiate, needs counsel or reject")
        if disp == "accept" and item.get("severity") == "Serious" and len(reason) < 10:
            raise ValueError("Accepting a Serious item needs a written reason (at least a sentence) - GR-05")
        decisions[item_id] = {"disposition": disp, "reason": reason, "by": user, "at": store.now(),
                              "exception": disp == "accept" and item.get("severity") == "Serious",
                              "title": item.get("title") or item.get("why", "")[:80]}
        state["status"].setdefault(doc_id, {})["stage"] = "In review (Karandeep)"
        store.save(state)
        store.audit("disposition", user, doc_id=doc_id, item_id=item_id, disposition=disp, reason=reason,
                    severity=item.get("severity"), logged_as_exception=decisions[item_id]["exception"])
        return self.send(200, {"decisions": decisions, "gate": R.gate(doc_id)})

    def api_post_ready(self, _, qs):
        user = self.user()
        if USERS[user]["role"] != "reviewer":
            raise Forbidden("Only Karandeep can mark a contract ready for his signature")
        doc_id = self.body()["doc_id"]
        g = R.gate(doc_id)
        if not g["ready_enabled"]:
            raise ValueError(f"{len(g['open'])} Serious finding(s) or possible conflict(s) still need a disposition - GR-10")
        state = store.load()
        state["status"].setdefault(doc_id, {})["stage"] = "Ready for Karandeep's signature (signed by hand, outside CounterSign)"
        store.save(state)
        store.audit("marked_ready_to_sign", user, doc_id=doc_id, note="System signs nothing (GR-01)")
        return self.send(200, {"status": state["status"][doc_id]})

    def api_post_decide(self, _, qs):
        """Record that Karandeep signed (by hand) or rejected. On 'signed', obligations are extracted for confirmation."""
        user = self.user()
        if USERS[user]["role"] != "reviewer":
            raise Forbidden("Only Karandeep records the final decision")
        b = self.body()
        doc_id, decision = b["doc_id"], b["decision"]
        if decision not in ("signed", "rejected"):
            raise ValueError("decision must be signed or rejected")
        if decision == "signed" and not R.gate(doc_id)["ready_enabled"]:
            raise ValueError("Every Serious finding and possible conflict needs a disposition before recording a signature - GR-10")
        state = store.load()
        st = state["status"].setdefault(doc_id, {})
        st.update(stage="Signed (by Karandeep, by hand)" if decision == "signed" else "Rejected", decided=store.now(), decision=decision)
        extracted = []
        if decision == "signed":
            extracted = extract_promises(R.corpus()[doc_id])
            have = {e["id"] for e in state["register"]["extracted"]}
            state["register"]["extracted"].extend(e for e in extracted if e["id"] not in have)
        store.save(state)
        R.invalidate()
        store.audit("decision_recorded", user, doc_id=doc_id, decision=decision, promises_extracted=len(extracted),
                    informed=st.get("review_ready", "") < st["decided"])
        return self.send(200, {"status": st, "extracted": len(extracted)})

    def api_post_feedback(self, _, qs):
        b = self.body()
        state = store.load()
        state["feedback"][b["doc_id"]] = {"missed": b.get("missed"), "reason": b.get("reason", ""), "by": self.user(), "at": store.now()}
        store.save(state)
        store.audit("review_feedback", self.user(), doc_id=b["doc_id"], missed=b.get("missed"), reason=b.get("reason", ""))
        return self.send(200, {"ok": True})

    def api_get_counsel_pack(self, doc_id, qs):
        user = self.user()
        if USERS[user]["role"] != "reviewer":
            raise Forbidden("Only Karandeep prepares counsel packs")
        html = R.counsel_pack(doc_id, user)
        name = re.sub(r"[^a-z0-9]+", "-", R.corpus()[doc_id]["counterparty"].lower()).strip("-")
        return self.send(200, html, "text/html; charset=utf-8", {"Content-Disposition": f'attachment; filename="counsel-pack-{name}.html"'})

    def api_post_ask(self, _, qs):
        b = self.body()
        res = R.refuse_or_answer(b.get("question", ""), b.get("doc_id"))
        store.audit("question", self.user(), doc_id=b.get("doc_id"), question=b.get("question", "")[:300], refused=res["refused"])
        return self.send(200, res)

    # ------------------------------------------------------------ register
    def api_get_register(self, _, qs):
        entries = R.register_entries()
        return self.send(200, {"entries": entries, "coverage": coverage(entries)})

    def api_get_register_search(self, _, qs):
        entries = [e for e in R.register_entries() if e.get("confirmed")]
        ind, country, svc = (qs.get("industry") or "").lower(), qs.get("country") or "", (qs.get("service") or "").lower()
        out = []
        for e in entries:
            if ind and not any(ind in i for i in e.get("industries", [])) and ind not in e["activity"].lower():
                continue
            if country and country not in e.get("geographies", []) and "*" not in e.get("geographies", []):
                continue
            if svc and not any(svc in s for s in e.get("services", [])) and svc not in e["activity"].lower():
                continue
            out.append(e)
        store.audit("register_search", self.user(), industry=ind, country=country, service=svc, results=len(out))
        return self.send(200, {"results": out, "coverage": coverage(R.register_entries())})

    def api_post_register_confirm(self, _, qs):
        user = self.user()
        if not (USERS[user].get("custodian") or USERS[user]["role"] == "reviewer"):
            raise Forbidden("Only the register custodian (Jay) or Karandeep confirms register entries")
        b = self.body()
        entry = next(e for e in R.register_entries() if e["id"] == b["entry_id"])
        edits = {k: v for k, v in (b.get("edits") or {}).items() if k in ("end", "activity", "geographies", "industries", "label", "affiliates")}
        state = store.load()
        state["register"]["confirmations"][entry["id"]] = {"by": user, "on": store.now(), "edits": edits}
        store.save(state)
        R.invalidate()
        store.audit("register_confirmed", user, entry_id=entry["id"], counterparty=entry["counterparty"], edits=edits)
        return self.send(200, {"ok": True})

    # ------------------------------------------------------------ intake
    def api_post_upload(self, _, qs):
        user = self.user()
        b = self.body()
        meta = b.get("meta") or {}
        if meta.get("informal") not in ("yes", "no"):
            raise ValueError("Answer the required question: was anything agreed outside this document?")
        if meta.get("informal") == "yes" and not (meta.get("informal_note") or "").strip():
            raise ValueError("Describe what was agreed outside the document")
        data = base64.b64decode(b["data"])
        text, notes = extract_text(b["filename"], data)
        scan = phi_scan(text)
        if scan["block"]:
            store.audit("upload_blocked_phi", user, filename=b["filename"], hits=scan["hits"])
            raise ValueError("Upload blocked: this file looks like it contains patient or bulk personal data (" +
                             ", ".join(f"{v} {k}" for k, v in scan["hits"].items()) + "). CounterSign reads contracts, not datasets (FR-05).")
        uid = "up-" + hashlib.sha1(data).hexdigest()[:10]
        store.UPLOADS.mkdir(parents=True, exist_ok=True)
        stored = uid + ".md"
        (store.UPLOADS / stored).write_text(text, encoding="utf-8")
        state = store.load()
        meta = {k: meta.get(k) for k in ("counterparty", "doc_type", "side", "service_region", "value", "currency", "deadline",
                                          "seller", "deal", "informal", "informal_note", "parent")}
        meta["value"] = float(meta["value"]) if meta.get("value") not in (None, "") else None
        meta["seller"] = meta.get("seller") or user
        meta["received"] = TODAY.isoformat()
        state["uploads"][uid] = {"stored": stored, "filename": b["filename"], "meta": meta, "by": user, "at": store.now(),
                                 "notes": notes, "phi_warning": scan["hits"] if scan["warn"] else None}
        state["status"][uid] = {"stage": "Received", "received": store.now()}
        store.save(state)
        R.invalidate()
        store.audit("upload", user, doc_id=uid, filename=b["filename"], counterparty=meta.get("counterparty"),
                    informal=meta.get("informal"), extraction_notes=notes, phi_warning=bool(scan["warn"]))
        return self.send(200, {"id": uid, "notes": notes, "phi_warning": scan["hits"] if scan["warn"] else None})

    def api_post_prefill(self, _, qs):
        """Pre-fill deal context from the document itself (FR-02); the seller confirms."""
        b = self.body()
        text, notes = extract_text(b["filename"], base64.b64decode(b["data"]))
        d = R._doc_from("uploads/preview.md", text, {}, "upload")
        side = "nda" if re.search(r"non-?disclosure|\bNDA\b", d["title"], re.I) else (
            "buyer" if any(l in ("Company", "AtliQ") for l in d["labels"]["atliq"][1:]) and any(
                l in ("Contractor", "Vendor", "Subcontractor", "Consultant") for l in d["labels"]["other"]) else
            "partner" if "Partner" in d["labels"]["atliq"] else "supplier")
        value = None
        m = re.search(r"(?:USD|US\$|\$)\s?([\d,]{4,})", text)
        if m:
            value = float(m.group(1).replace(",", ""))
        return self.send(200, {"counterparty": d["counterparty"], "doc_type": d["title"].title()[:60], "side": side,
                               "entity_named": d["entity_named"], "value": value, "clauses": len(d["clauses"]), "notes": notes})

    # ------------------------------------------------------------ audit, evals, admin
    def api_get_audit(self, _, qs):
        return self.send(200, {"events": store.read_audit(int(qs.get("limit", 300)))})

    def api_get_evals(self, _, qs):
        from evals.run_evals import scenarios
        res = scenarios()
        store.audit("evals_run", self.user(), passed=sum(r["passed"] for r in res), total=len(res))
        return self.send(200, {"results": res})

    def api_get_metrics(self, _, qs):
        state = store.load()
        decided = {k: v for k, v in state["status"].items() if v.get("decided")}
        informed = 0
        for k, v in decided.items():
            dec = state["decisions"].get(k, {})
            try:
                r = R.get_review(k)
            except KeyError:
                continue
            complete = v.get("review_ready", "9") < v["decided"] and not R.open_items(r, dec) and all(f["verified"] for f in r["findings"])
            informed += complete
        fb = state["feedback"]
        acc = [d for dd in state["decisions"].values() for d in dd.values()]
        serious_acc = [d for d in acc if d.get("exception")]
        return self.send(200, {"decisions": len(decided), "informed": informed,
                               "idr": (informed / len(decided)) if decided else None,
                               "feedback_answered": len(fb), "feedback_missed": sum(1 for f in fb.values() if f.get("missed") == "yes"),
                               "dispositions": len(acc), "serious_accepted_as_exception": len(serious_acc)})

    def api_post_reset(self, _, qs):
        if USERS[self.user()]["role"] != "reviewer":
            raise Forbidden("Only Karandeep can reset the demo")
        store.reset()
        R.invalidate()
        R._cache.clear()
        return self.send(200, {"ok": True})


def main():
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"CounterSign running at http://localhost:{PORT}  ({DISCLAIMER})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
