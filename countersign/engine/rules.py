"""Deterministic rule engines: entity / law / invoicing (FR-16) and deal bundle + flow-downs (FR-17 - FR-20).

No AI here: these are fact comparisons against finance's entity sheet and the
bundle rule table (PRD 5.1).
"""

import re

from .checks import fid
from .knowledge import BUNDLE_RULES, ENTITY_RULES, FACTS, LAW_PATTERNS
from .text import best_quote, sentences


def _expected_entity(region):
    return "Inc" if (region or "").strip().upper() in ("USA", "US", "UNITED STATES") else "Pvt Ltd"


def _law(clauses):
    for c in clauses:
        for s in sentences(c["text"]):
            if re.search(r"governed by|governing law", s, re.I):
                for rx, fam in LAW_PATTERNS:
                    if re.search(rx, s):
                        return fam, c, s
    return None, None, None


def _forum(clauses):
    for c in clauses:
        for s in sentences(c["text"]):
            if re.search(r"arbitration|courts|jurisdiction|venue", s, re.I) and not re.search(r"governed by", s, re.I):
                for rx, label, fam in [(r"SIAC|Singapore", "SIAC arbitration, Singapore", "Singapore"),
                                       (r"LCIA|London", "London", "England & Wales"),
                                       (r"Riyadh", "Riyadh courts", "Saudi Arabia"),
                                       (r"Dubai International Financial Centre", "DIFC courts", "UAE"),
                                       (r"Dubai", "Dubai courts", "UAE"),
                                       (r"Munich", "Munich courts", "Germany"),
                                       (r"San Francisco", "San Francisco courts", "USA"),
                                       (r"Harris County|Travis County|Texas", "Texas courts", "USA"),
                                       (r"Mumbai|Pune|Bengaluru|New Delhi|India", "Indian courts / seat", "India")]:
                    if re.search(rx, s):
                        return label, fam, c, s
    return None, None, None, None


def check_entity(ctx):
    doc = ctx.doc
    rows = []
    named = doc.get("entity_named")
    expected = _expected_entity(doc.get("service_region"))
    party_clause = next((c for c in ctx.clauses if re.search(r"AtliQ (Inc|Technologies)|ATLIQ (INC|TECHNOLOGIES)", c["text"])), ctx.clauses[0])
    party_quote = best_quote(party_clause["text"], r"AtliQ Inc|AtliQ Technologies|ATLIQ")
    exp_name = ENTITY_RULES[expected]["name"]
    if named:
        ok = named == expected
        rows.append({"check": "Signing entity", "expected": f"{exp_name} (service region: {doc.get('service_region')})",
                     "found": ENTITY_RULES[named]["name"], "status": "ok" if ok else "mismatch", "ref": party_clause["ref"]})
        if not ok:
            ctx.add("entity", "Serious", "P5", "Wrong AtliQ entity for this region",
                    f"{doc.get('service_region')} work belongs to {exp_name} per finance's entity sheet ('{ENTITY_RULES[expected]['serves']}'), but the parties clause names {ENTITY_RULES[named]['name']}. The entity decides who invoices, the tax regime and the bank account; mismatches delayed payment twice in 2025.",
                    party_clause, r"AtliQ Inc|AtliQ Technologies|ATLIQ", category="Entity & law", quote=party_quote)
    # invoicing entity
    for c in ctx.clauses:
        if c is party_clause:
            continue
        for s in sentences(c["text"]):
            if re.search(r"invoice", s, re.I) and re.search(r"raised by AtliQ Technologies|GSTIN", s):
                inv = "Pvt Ltd"
                status = "ok" if inv == named else "mismatch"
                rows.append({"check": "Invoicing entity", "expected": ENTITY_RULES[named or expected]["name"] + " (same as parties clause)",
                             "found": "AtliQ Technologies Pvt Ltd (GSTIN)", "status": status, "ref": c["ref"]})
                if status == "mismatch":
                    ctx.add("invoicing", "Serious", "P5", "Invoicing entity differs from contracting entity",
                            "The parties clause names AtliQ Inc but invoices are raised by AtliQ Technologies Pvt Ltd under its Indian GSTIN.",
                            c, r"raised by|GSTIN", category="Entity & law")
    fam, lc, ls = _law(ctx.clauses)
    if fam:
        want = "USA" if expected == "Inc" else "India"
        ok = fam.startswith(want)
        sev = None if ok else ("Serious" if expected == "Inc" else "Review")
        rows.append({"check": "Governing law", "expected": "US state law" if want == "USA" else "Indian law",
                     "found": fam, "status": "ok" if ok else ("mismatch" if sev == "Serious" else "review"), "ref": lc["ref"]})
        if sev:
            ctx.add("law", sev, "P5", f"Governing law: {fam}",
                    (f"{fam} law on a {ENTITY_RULES[expected]['name']} contract. " +
                     ("AtliQ Inc under foreign law is the Brightwater pattern." if expected == "Inc" else
                      "Foreign law is acceptable only as a logged, deliberate exception (Northwind English law, Al Noor DIFC).")),
                    lc, r"governed by|laws of", category="Entity & law")
    else:
        rows.append({"check": "Governing law", "expected": "-", "found": "not stated in this document (may follow the parent agreement)", "status": "review", "ref": "-"})
    flabel, ffam, fc, fs = _forum(ctx.clauses)
    if flabel:
        want = "USA" if expected == "Inc" else "India"
        ok = ffam == want or (fam and ffam and fam.startswith(ffam))
        rows.append({"check": "Disputes forum", "expected": "US courts" if want == "USA" else "Indian courts / seat",
                     "found": flabel, "status": "ok" if ok else "review", "ref": fc["ref"]})
        if not ok and expected == "Inc" and fam and fam.startswith("USA"):
            ctx.add("forum", "Review", "P5", f"Disputes go to {flabel}",
                    f"US law but disputes are resolved by {flabel}: AtliQ Inc would litigate outside the US.",
                    fc, r"arbitration|courts", category="Entity & law")
    return rows


# --------------------------------------------------------------------------- bundles

def _find(docs, rx):
    for d in docs:
        for c in d["clauses"]:
            for s in sentences(c["text"]):
                if re.search(rx, s):
                    return d, c, s
    return None, None, None


def _issue(deal, key, severity, principle, title, reason, d, c, s):
    return {"id": fid(deal, key), "key": key, "severity": severity, "principle": principle, "title": title,
            "reason": reason, "clause_ref": c["ref"] if c else "-", "quote": s or "", "source_file": d["file"] if d else None,
            "source_title": d["title"] if d else None, "category": "Bundle & flow-down", "origin": "rule", "precedents": []}


def check_bundle(deal_key, deal, docs, signed_members, related_signed):
    """docs: parsed incoming docs in the deal; signed_members / related_signed: parsed signed docs."""
    items, issues = [], []
    data_types = deal.get("data_types", [])
    client_docs = [d for d in docs if d["side"] in ("supplier", "partner")]
    vendor_docs = [d for d in docs if d["side"] == "buyer"]
    every = docs + signed_members

    def has(rx_type):
        for d in signed_members:
            if re.search(rx_type, d["title"] + " " + d["file"], re.I):
                return d, "Signed"
        for d in docs:
            if re.search(rx_type, d["doc_type"] + " " + d["title"], re.I):
                return d, "Draft - in review"
        return None, "Missing"

    if "PHI" in data_types:
        rule = BUNDLE_RULES["PHI"]
        for t, rx in [("NDA", r"\bNDA\b|non-?disclosure"), ("MSA", r"\bMSA\b|MASTER .*SERVICES"), ("BAA (with client)", r"\bBAA\b|BUSINESS ASSOCIATE")]:
            d, st = has(rx)
            if t.startswith("NDA"):
                d2 = next((x for x in signed_members if re.search(r"nda", x["file"])), None)
                d, st = (d2, "Signed") if d2 else (d, st)
            items.append({"doc": t, "status": st, "file": d["file"] if d else None})
        flow_d, flow_c, flow_s = _find(docs, r"agrees in writing, prior to any access to PHI")
        us_d, us_c, us_s = _find(docs, r"organized under the laws of a State of the United States")
        for v in vendor_docs:
            name = v["counterparty"]
            sub = next((x for x in every if re.search(r"BAA|BUSINESS ASSOCIATE", x["title"], re.I) and name.split()[0] in x["text"][:2000]), None)
            items.append({"doc": f"Subcontractor BAA - {name}", "status": "Signed" if sub else "Missing", "file": sub["file"] if sub else None})
            if not sub:
                issues.append(_issue(deal_key, f"subbaa-{name}", "Serious", "P11", f"Subcontractor BAA - {name}: missing",
                                     f"{name} will build pipelines from the EHR, but no written flow-down BAA exists. The client BAA requires one signed before any PHI access, and the client's prior written approval of the subcontractor.",
                                     flow_d, flow_c, flow_s))
        # AtliQ Pvt Ltd (Pune) as an Affiliate subcontractor
        ic = next((x for x in related_signed if "intercompany" in x["file"]), None)
        if ic:
            m = re.search(r"\"\*\*Engagement\*\*\" means the (\w+) Engagement", ic["text"])
            scope = m.group(1) if m else "another"
            covers = scope.lower() in deal["client"].lower()
            items.append({"doc": "Intercompany BAA (AtliQ Inc -> AtliQ Pvt Ltd)", "status": "Signed - covers this deal" if covers else f"Signed - covers {scope} only",
                          "file": ic["file"]})
            if not covers:
                ic_c = next(c for c in ic["clauses"] if '"**Engagement**" means' in c["text"])
                issues.append(_issue(deal_key, "icbaa", "Serious", "P11", f"Intercompany BAA covers {scope} only",
                                     f"The Pune team's only BAA is limited to the {scope} engagement and to de-identified data. It does not cover {deal['client']}; never assume a past agreement covers a new deal.",
                                     ic, ic_c, best_quote(ic_c["text"], r"Engagement")))
        if us_c:
            issues.append(_issue(deal_key, "us-org", "Serious", "P11", "AtliQ Pvt Ltd cannot be an approved subcontractor",
                                 f"Delivery sits in {FACTS['delivery_location']['value']}, but the BAA requires every subcontractor (including Affiliates) to be US-organised with US-located personnel.",
                                 us_d, us_c, us_s))
        off_d, off_c, off_s = _find(docs, r"located outside the United States shall access only de-identified")
        ban_d, ban_c, ban_s = _find(docs, r"outside the United States, whether directly or by remote access")
        if off_c and ban_c:
            issues.append(_issue(deal_key, "contradiction", "Review", "FR-20", "Possible contradiction between MSA and BAA",
                                 f"MSA {off_c['ref']} lets offshore personnel access de-identified data; BAA {ban_c['ref']} bars any access outside the US. Show both; confirm which governs with counsel (the BAA controls as to PHI).",
                                 off_d, off_c, off_s))
        appr_d, appr_c, appr_s = _find(docs, r"shall not subcontract any portion of the Services without Client's prior written consent")
        if appr_c and vendor_docs:
            issues.append(_issue(deal_key, "approval", "Review", "P11", "Client approval needed for subcontractors",
                                 "Harrington must approve each subcontractor in writing before they start (" + ", ".join(v["counterparty"] for v in vendor_docs) + ").",
                                 appr_d, appr_c, appr_s))

    if "EU_PD" in data_types:
        dpa_present = any(re.search(r"Annex 3", " ".join(h for h in re.findall(r"^\s*#+\s+(.*)$", d["text"], re.M))) for d in client_docs)
        items.append({"doc": "Services agreement", "status": "Draft - in review", "file": client_docs[0]["file"] if client_docs else None})
        items.append({"doc": "DPA (Art. 28) with SCCs - Annex 3", "status": "Attached" if dpa_present else "Missing (referenced, not attached)", "file": None})
        sc_d, sc_c, sc_s = _find(client_docs, r"may subcontract parts of the services only with Client's prior written consent")
        excl_d, excl_c, excl_s = _find(client_docs, r"exclusive, perpetual, transferable and unrestricted right of use")
        for v in vendor_docs:
            items.append({"doc": f"Subcontractor agreement - {v['counterparty']}", "status": "Draft (AtliQ paper)", "file": v["file"]})
            if sc_c:
                issues.append(_issue(deal_key, f"consent-{v['counterparty']}", "Review", "P11", f"Client consent needed to subcontract to {v['counterparty']}",
                                     "The client contract allows subcontracting only with prior written consent.", sc_d, sc_c, sc_s))
            handles_pd = re.search(r"technician names|personal data|names", v["text"], re.I)
            has_gdpr = re.search(r"GDPR|Article 28|Art\. 28|data processing|sub-processor", v["text"], re.I)
            if handles_pd and not has_gdpr:
                c = next((c for c in v["clauses"] if re.search(r"technician names|names", c["text"])), v["clauses"][-1])
                issues.append(_issue(deal_key, f"gdpr-{v['counterparty']}", "Serious", "P11", f"No GDPR sub-processor terms with {v['counterparty']}",
                                     "The vendor will handle EU personal data (technician names) but its draft has no data-processing terms - GDPR Art. 28(4) requires them in writing before access.",
                                     v, c, best_quote(c["text"], r"technician names|names")))
            vip = next((c for c in v["clauses"] if re.search(r"retain all right, title and interest[^.]*annotation outputs", c["text"])), None)
            if vip and excl_c:
                issues.append(_issue(deal_key, f"ipflow-{v['counterparty']}", "Serious", "P6", f"IP flow-down gap with {v['counterparty']}",
                                     f"{v['counterparty']} keeps the IP in the annotation outputs and grants AtliQ only a non-exclusive licence, while AtliQ must give the client exclusive rights in all Work Results ({excl_c['ref']}).",
                                     v, vip, best_quote(vip["text"], r"retain all right")))

    if not data_types:
        for d in signed_members:
            items.append({"doc": d["title"].title()[:60], "status": "Signed - on file", "file": d["file"]})
        for d in docs:
            items.append({"doc": f"{d['doc_type']} - {d['counterparty']}", "status": "Draft - in review", "file": d["file"]})
        if deal_key == "lakeshore":
            mr = next((d for d in vendor_docs if d.get("entity_named") == "Pvt Ltd"), None)
            if mr:
                c = mr["clauses"][0]
                issues.append(_issue(deal_key, "staffing-entity", "Review", "P5", f"{mr['counterparty']} on the wrong entity's template",
                                     "The client contract is with AtliQ Inc, but the contractor is engaged by AtliQ Pvt Ltd on the India template.",
                                     mr, c, best_quote(c["text"], r"AtliQ Technologies")))
    return {"deal": deal_key, "name": deal["name"], "data_types": [BUNDLE_RULES[t]["label"] for t in data_types],
            "flowdown_rule": [BUNDLE_RULES[t]["flowdown"] for t in data_types], "documents": items, "issues": issues}
