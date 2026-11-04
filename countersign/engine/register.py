"""Promise Register (FR-21 - FR-26) and coverage (FR-29)."""

import csv
import re
from datetime import date

from .knowledge import (NO_COVENANT_FILES, PLACES, REGISTER_SEED, SIGNED_FILE_TRACKER, TODAY)
from .text import DATASET, best_quote, read_dataset_file, sentences, verify_quote


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def compute_end(rule):
    if rule[0] == "permanent":
        return None
    if rule[0] == "fixed":
        return date.fromisoformat(rule[1])
    if rule[0] == "add_months":
        return add_months(date.fromisoformat(rule[1]), rule[2])
    return None


def build_register(state_register):
    """Seed entries + any extracted entries, with verification, dates, status and confirmation state."""
    entries = []
    for seed in REGISTER_SEED:
        e = dict(seed)
        src = read_dataset_file("signed_contracts/" + e["file"])
        e["anchor_checks"] = [{"quote": a, "verified": verify_quote(a, src)} for a in e["anchors"]]
        e["verified"] = all(a["verified"] for a in e["anchor_checks"])
        end = compute_end(e["end_rule"])
        e["end"] = end.isoformat() if end else None
        if e.get("status_override"):
            e["status"] = e["status_override"]
        elif end is None:
            e["status"] = "permanent"
        else:
            e["status"] = "active" if end >= TODAY else "expired"
        e["source"] = "back-fill"
        entries.append(e)
    entries.extend(state_register.get("extracted", []))
    for e in entries:
        st = state_register.get("confirmations", {}).get(e["id"])
        if st:
            e["confirmed"] = True
            e["confirmed_by"], e["confirmed_on"] = st["by"], st["on"]
            e.update(st.get("edits", {}))
        elif e.get("confirmed") and e.get("source") == "back-fill":
            e.setdefault("confirmed_by", "Jay (register custodian) - day-one back-fill")
            e.setdefault("confirmed_on", "2026-09-28")
        if e.get("low_confidence") or not e.get("verified", True):
            if not st:
                e["confirmed"] = False  # GR-04: low-confidence reads are forced to review
        e.pop("end_rule", None)
    return entries


def tracker_rows():
    with open(DATASET / "contract_tracker.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def coverage(entries):
    rows = tracker_rows()
    signed = [r for r in rows if r["status"].strip() == "Signed"]
    seen, unique, dups = set(), [], []
    for r in signed:
        key = (r["counterparty"], r["doc_type"], r["signed_date"])
        if key in seen:
            dups.append(r["contract_id"])
            continue
        seen.add(key)
        unique.append(r)
    on_file = {cid for ids in SIGNED_FILE_TRACKER.values() for cid in ids}
    covered = [r for r in unique if r["contract_id"] in on_file]
    missing = [r for r in unique if r["contract_id"] not in on_file]
    low = [e for e in entries if e.get("low_confidence")]
    pending = [e for e in entries if not e.get("confirmed")]
    restrictive_filled = sum(1 for r in rows if r["restrictive_clauses"].strip())
    line = (f"Checked {len(covered)} of {len(unique)} signed records; {len(missing)} not on file; "
            f"{len(low)} low-confidence scan")
    if pending:
        line += f"; {len(pending)} register entr{'y' if len(pending) == 1 else 'ies'} pending confirmation (not used)"
    return {"line": line, "covered": len(covered), "total": len(unique), "missing": [
        {"id": r["contract_id"], "counterparty": r["counterparty"], "doc_type": r["doc_type"], "signed": r["signed_date"]} for r in missing],
        "duplicates": dups, "files": len(SIGNED_FILE_TRACKER), "low_confidence": len(low), "pending": len(pending),
        "tracker_rows": len(rows), "restrictive_column_filled": restrictive_filled,
        "no_covenant_files": NO_COVENANT_FILES}


# ----------------------------------------------------------- extraction at signature (FR-21)

INDUSTRY_WORDS = {
    "hospitality": r"hotel|resort|serviced apartment|hospitality",
    "financial services": r"\bbank|NBFC|non-banking|wealth|broker|fintech|lending|financial services",
    "retail": r"retail|grocery|grocer",
    "cloud data platform": r"lakehouse|data warehouse|data-warehouse|unified analytics platform",
    "healthcare": r"health ?care|health system|\bhospitals?\b|\bpatients?\b|\bclinics?\b",
    "online travel agency": r"online travel agenc|travel-booking|travel planning app",
}

EXTRACT_PATTERNS = [
    ("Non-compete", r"(?:shall not|neither [^.]{0,40}? shall)[^.]{0,220}(provide|develop|act as|solicit, market to)[^.]{0,260}(Competitor|Competing|Hospitality Business|in competition|Account|online travel)"),
    ("Exclusivity", r"shall not act as an? [^.]*partner for any"),
    ("Most-favoured pricing", r"no less favou?rable than those offered"),
    ("IP assignment", r"pre-existing materials incorporated[^.]*(vest|assign)|Pre-Existing Materials incorporated[^.]*assign"),
    ("Data location", r"(stored|store|access)[^.]{0,80}only in India|outside the United States without"),
    ("Non-solicit", r"(solicit|hire or engage)[^.]{0,120}(employee|consultant)[^.]{0,120}\((\d+)\) months"),
]


def extract_promises(doc):
    """Propose register entries from a newly signed document. They join only after confirmation (GR-04)."""
    out = []
    by_ref = {c["ref"]: c["text"] for c in doc["clauses"]}
    for c in doc["clauses"]:
        for s in sentences(c["text"]):
            for typ, rx in EXTRACT_PATTERNS:
                if re.search(rx, s, re.I):
                    # definitions travel with the clause: 'Competitor' or 'GCC' are defined elsewhere
                    defs = " ".join(by_ref.get(d["ref"], "") for d in c.get("definitions", []) if re.search(r"\b" + re.escape(d["term"]) + r"\b", s))
                    scope = s + " " + defs
                    geos = sorted({v for k, v in PLACES.items() if re.search(r"\b" + re.escape(k) + r"\b", scope)})
                    if re.search(r"\bGCC\b", scope):
                        geos = sorted(set(geos) | {"United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman"})
                    ind = [k for k, rxi in INDUSTRY_WORDS.items() if re.search(rxi, scope, re.I)]
                    months = re.search(r"\((\d+)\) months", s)
                    out.append({
                        "id": f"X-{doc['id']}-{c['ref']}-{typ[:4]}".replace("§", "s").replace(" ", ""),
                        "counterparty": doc["counterparty"], "type": typ, "file": doc["file"], "clauses": c["ref"],
                        "entity": "AtliQ Inc" if doc.get("entity_named") == "Inc" else "AtliQ Technologies Pvt Ltd",
                        "affiliates": bool(re.search(r"Affiliates", s)), "activity": best_quote(s, rx, 300),
                        "industries": ind, "services": [], "geographies": geos or ["*"],
                        "start": TODAY.isoformat(), "end": None,
                        "end_note": f"{months.group(1)} months after the term - set the end date on confirmation" if months else "Set on confirmation",
                        "anchors": [s], "anchor_checks": [{"quote": s, "verified": True}], "verified": True,
                        "label": "standard", "confirmed": False, "status": "active", "source": "extracted at signature",
                        "low_confidence": doc.get("ocr", {}).get("low_confidence", False)})
                    break
    return out
