"""AtliQ's own knowledge: principles, facts, rule tables, intake context and the
Promise Register back-fill.

Everything here is *AtliQ-owned context* (PRD section 7.1). Every factual claim
carries an anchor quote that is verified verbatim against its source file at
start-up (GR-02); anything that fails verification is shown as
"Not sure - please cross-check" instead of as fact.
"""

from datetime import date

# The dataset's "today" (README: treat today as 2026-09-28).
TODAY = date(2026, 9, 28)

PRINCIPLES_VERSION = "P-list v0.1 (draft for Karandeep to confirm, derived from the Mar-2024 checklist + confirmed precedents)"

# PRD 5.1 - draft principles list. No numeric threshold beyond what the
# checklist or a confirmed precedent states.
PRINCIPLES = {
    "P1": {"name": "Delay damages proportionate",
           "text": "Delay damages proportionate (precedent: 0.5%/week of the affected milestone, cap 5% of it) and never for client-caused delay.",
           "checklist": "LDs -> cap it. never open ended"},
    "P2": {"name": "Liability capped",
           "text": "Liability capped (checklist: 1x fees), never unlimited. A higher data-breach cap is a known precedent (CareBridge 2x).",
           "checklist": "liability -> 1x fees. NOT unlimited"},
    "P3": {"name": "Indemnity mutual",
           "text": "Indemnity mutual; never cover the other side's own negligence.",
           "checklist": "indemnity -> mutual. we don't cover their mistakes"},
    "P4": {"name": "Payment 30 days, 45 max",
           "text": "Payment 30 days, 45 max.",
           "checklist": "payment -> 30 days, 45 max"},
    "P5": {"name": "Law matches entity",
           "text": "Governing law matches the signing entity (India for Pvt Ltd, US for Inc); foreign law only as a logged, deliberate exception.",
           "checklist": "gov law -> ours (India for Pvt Ltd, US for Inc)"},
    "P6": {"name": "IP split",
           "text": "Client owns what AtliQ builds for it; AtliQ keeps its own tools (no assignment of pre-existing materials such as PipeKit).",
           "checklist": "IP -> client owns what we build for them, we keep our own stuff"},
    "P7": {"name": "Paid for work done",
           "text": "On termination, AtliQ is paid for work done.",
           "checklist": "termination -> they pay for work done"},
    "P8": {"name": "NDAs mutual in substance",
           "text": "NDAs mutual in substance, with no hidden non-competes or one-way residuals.",
           "checklist": "NDAs -> just sign if mutual"},
    "P9": {"name": "Past promises honoured",
           "text": "Never breach a promise already made (non-compete, exclusivity, MFN, IP).",
           "checklist": "(Karandeep's Sep-2026 note: 'what we've already promised other clients')"},
    "P10": {"name": "Own paper is fair",
            "text": "AtliQ's own paper gives counterparties P1-P4 and P7.",
            "checklist": "(Karandeep's Sep-2026 note: 'the same clause I'd reject from a client is sitting in our own template')"},
    "P11": {"name": "Data obligations flow down",
            "text": "Data obligations flow down, in writing, before data moves.",
            "checklist": "(Harrington BAA s4.3; GDPR Art. 28)"},
}

SEVERITY_ORDER = {"Serious": 0, "Review": 1, "Minor": 2}

# --------------------------------------------------------------------------
# Rule tables (deterministic - PRD 5.1 "an LLM adds risk and no value")
# --------------------------------------------------------------------------

GCC = ["United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman"]
EU_EEA = ["Germany", "France", "Netherlands", "Ireland", "Spain", "Italy", "Belgium", "Austria",
          "Sweden", "Denmark", "Finland", "Poland", "Portugal", "Norway", "Iceland", "Liechtenstein"]
EUROPE = EU_EEA + ["United Kingdom", "Switzerland"]

# Place names -> country, used to read geographies out of contract text.
PLACES = {
    "United Arab Emirates": "United Arab Emirates", "UAE": "United Arab Emirates", "Dubai": "United Arab Emirates",
    "Abu Dhabi": "United Arab Emirates", "Ras Al Khaimah": "United Arab Emirates", "Emirate": "United Arab Emirates",
    "Saudi": "Saudi Arabia", "KSA": "Saudi Arabia", "Riyadh": "Saudi Arabia", "Jeddah": "Saudi Arabia",
    "Dammam": "Saudi Arabia", "Madinah": "Saudi Arabia", "AlUla": "Saudi Arabia",
    "Qatar": "Qatar", "Doha": "Qatar", "Kuwait": "Kuwait", "Bahrain": "Bahrain", "Manama": "Bahrain",
    "Oman": "Oman", "Muscat": "Oman",
    "India": "India", "Mumbai": "India", "Pune": "India", "Bengaluru": "India", "Kochi": "India",
    "Germany": "Germany", "Munich": "Germany", "München": "Germany", "DACH": "Germany",
    "United Kingdom": "United Kingdom", "England": "United Kingdom", "London": "United Kingdom",
    "Singapore": "Singapore",
    "United States": "USA", "USA": "USA", "Texas": "USA", "Illinois": "USA", "Delaware": "USA",
    "California": "USA", "New Jersey": "USA", "Chicago": "USA", "Houston": "USA", "Austin": "USA",
    "Europe": "Europe", "European Union": "Europe",
}

# Governing-law keywords -> jurisdiction family
LAW_PATTERNS = [
    (r"laws? of India|Indian law|laws of the Republic of India", "India"),
    (r"State of Texas|laws of Texas", "USA (Texas)"),
    (r"State of Illinois", "USA (Illinois)"),
    (r"State of Delaware", "USA (Delaware)"),
    (r"State of New York", "USA (New York)"),
    (r"State of California", "USA (California)"),
    (r"State of New Jersey", "USA (New Jersey)"),
    (r"England and Wales|English law", "England & Wales"),
    (r"Dubai International Financial Centre", "DIFC (UAE)"),
    (r"Emirate of Dubai|United Arab Emirates", "Dubai / UAE"),
    (r"Kingdom of Saudi Arabia", "Saudi Arabia"),
    (r"Federal Republic of Germany", "Germany"),
    (r"laws of Singapore|Singapore law", "Singapore"),
]

ENTITY_RULES = {
    "Inc": {"name": "AtliQ Inc", "serves": "Clients in the United States only", "law_family": "USA"},
    "Pvt Ltd": {"name": "AtliQ Technologies Pvt Ltd", "serves": "Clients in India, the Middle East, Europe and any region outside the US", "law_family": "India"},
}

# Deal type x data type -> required companion documents (PRD FR-17).
BUNDLE_RULES = {
    "PHI": {"label": "US patient data (HIPAA PHI)",
            "client_docs": ["NDA", "MSA", "BAA"],
            "flowdown": "Subcontractor BAA signed before any PHI access, for every subcontractor, freelancer or Affiliate (incl. AtliQ Pvt Ltd)",
            "law": "45 C.F.R. 164.502(e) / 164.308(b)"},
    "EU_PD": {"label": "EU personal data (GDPR)",
              "client_docs": ["MSA", "DPA (Art. 28) with SCCs"],
              "flowdown": "Written GDPR Art. 28(4) sub-processor terms with every subcontractor before data access, plus client consent to subcontract",
              "law": "GDPR Art. 28"},
}

# --------------------------------------------------------------------------
# AtliQ facts table (FR-19) - every fact anchored to a source file.
# --------------------------------------------------------------------------

FACTS = {
    "cyber_cover_usd": {"value": 1_000_000, "label": "Cyber insurance held",
                        "source": "meeting_notes/2026-09-27_harrington_huddle.md",
                        "quote": "Our cyber policy is $1M btw, Harrington BAA wants 5."},
    "delivery_location": {"value": "Pune, India", "label": "Delivery teams (both entities)",
                          "source": "atliq_entities.md",
                          "quote": "Delivery teams for both entities sit in Pune"},
    "inc_scope": {"value": "USA only", "label": "AtliQ Inc serves",
                  "source": "atliq_entities.md", "quote": "Clients in **the United States only**"},
    "entity_mismatch_history": {"value": 2, "label": "Entity mismatches delayed payment in 2025",
                                "source": "atliq_entities.md",
                                "quote": "Mismatches between the contracting entity and the invoicing entity have caused payment delays twice in 2025."},
    "cloudspan_certified": {"value": 4, "label": "CloudSpan-certified engineers committed",
                            "source": "signed_contracts/2025-09-01_cloudspan_strategic_partnership_agreement.md",
                            "quote": "Partner shall maintain, throughout the Term, not fewer than four (4) Certified Engineers."},
}

# Operational events the product must surface as "act now" (PRD 13.3). They come
# from meeting notes whose italic editorial lines the README declares ground truth.
EVENTS = [
    {"id": "EV-PHI", "deal": "harrington",
     "title": "PHI received before any BAA - act now (outside the product)",
     "detail": "A sample extract with names, DOBs and diagnosis codes was forwarded to two Pune engineers on 12 Sep. The signed Harrington NDA excludes PHI until a BAA is signed, and the draft BAA bars any PHI access outside the US. Contain, assess and take counsel's advice.",
     "sources": [
         {"file": "meeting_notes/2026-09-27_harrington_huddle.md",
          "quote": "Pranav opened it here and forwarded to Sneha and Vikram in Pune to start profiling."},
         {"file": "meeting_notes/2026-09-27_harrington_huddle.md",
          "quote": "the sample extract remained with the two Pune engineers"},
         {"file": "signed_contracts/2026-08-20_harrington_health_mutual_nda.md",
          "quote": "Protected Health Information, as defined at 45 C.F.R. § 160.103, is excluded from this Agreement and shall be disclosed only after execution of a Business Associate Agreement between the Parties."},
     ]},
    {"id": "EV-COUNSEL", "deal": "gulfcrown",
     "title": "Counsel needs every restrictive contract by Thu 1 Oct",
     "detail": "Mehta Rao will not advise on Gulf Crown in isolation; turnaround is 5-7 working days from a complete set. Use 'Needs counsel' to prepare the pack (Al Noor MSA, Oman waiver, draft).",
     "sources": [
         {"file": "meeting_notes/2026-09-25_call_with_counsel_gulf_crown.md",
          "quote": "I can't advise on one in isolation"},
     ]},
]

# Who AtliQ works for, by industry (used for reverse conflicts such as an NDA
# non-compete that would bite existing clients). Source: signed files + tracker.
CLIENT_DIRECTORY = [
    {"name": "Trustline NBFC", "industry": "financial services", "country": "India", "status": "Signed MSA to 14 Aug 2027",
     "source": "signed_contracts/2026-08-15_trustline_nbfc_msa.md", "quote": "shall store Company Data only in India"},
    {"name": "PayTrack Technologies", "industry": "financial services", "country": "India", "status": "Signed MSA to 21 Jan 2027",
     "source": "signed_contracts/2025-01-22_paytrack_technologies_msa.md", "quote": "payment system data subject to RBI data localisation requirements"},
    {"name": "FinEdge Bank", "industry": "financial services", "country": "India", "status": "MSA in negotiation (tracker C-022)",
     "source": "contract_tracker.csv", "quote": "C-022,FinEdge Bank,MSA,Pvt Ltd,India"},
]

# --------------------------------------------------------------------------
# Negotiation precedents (FR-33) - labelled 'unreviewed' (Jay's reconstruction).
# --------------------------------------------------------------------------

PRECEDENTS = [
    {"id": "PR-ACME", "principles": ["P1"], "counterparty": "Acme Retail (2025)",
     "quote": "Open-ended isn't something we can sign.", "outcome": "LD 0.5%/week of milestone, cap 5%, client delays excluded"},
    {"id": "PR-TRUSTLINE", "principles": ["P1", "P4"], "counterparty": "Trustline NBFC (2026)",
     "quote": "K: 45 days; 0.5% of milestone fee per week, cap 5% of milestone, client delays excluded. Agreed.",
     "outcome": "45-day payment; P1 LD"},
    {"id": "PR-NORTHWIND-LD", "principles": ["P1"], "counterparty": "Northwind (2025)",
     "quote": "K countered 0.5%/week of milestone, cap 5% of milestone, client delays excluded. Agreed.",
     "outcome": "P1 LD on client paper"},
    {"id": "PR-ALNOOR-LD", "principles": ["P1"], "counterparty": "Al Noor (2025) - EXCEPTION",
     "quote": "Approving 10% of total fees as a strategic exception for Al Noor only — not our new standard.",
     "outcome": "Deliberate exception - never a default"},
    {"id": "PR-KESSLER", "principles": ["P2"], "counterparty": "Kessler Mobility (2026)",
     "quote": "Unlimited liability on a €120k deal means one bad incident … and the company is gone.",
     "outcome": "Walked away"},
    {"id": "PR-PAYTRACK", "principles": ["P3"], "counterparty": "PayTrack (2025)",
     "quote": "we can't insure against PayTrack's own negligence", "outcome": "Mutual indemnity agreed"},
    {"id": "PR-NORTHWIND-LAW", "principles": ["P5"], "counterparty": "Northwind (2025) - EXCEPTION",
     "quote": "English law / LCIA — not worth losing the deal over.", "outcome": "Deliberate foreign-law exception"},
    {"id": "PR-GLOBALMART", "principles": ["P8"], "counterparty": "GlobalMart (2026)",
     "quote": "We only sign mutual — we'll be sharing our architecture too.", "outcome": "One-way NDA replaced by mutual"},
    {"id": "PR-PIXELCRAFT", "principles": ["P10", "P1", "P2", "P4"], "counterparty": "PixelCraft (2025)",
     "quote": "I don't want our paper to be the thing I hate receiving.",
     "outcome": "Penalty deleted, 30-day payment, mutual cap at fees"},
    {"id": "PR-ROHAN", "principles": ["P10", "P6"], "counterparty": "Rohan Iyer (2025)",
     "quote": "my visuals library is the only thing I really own as a freelancer",
     "outcome": "Freelancer kept IP; AtliQ licence; 30-day pay; mutual cap"},
    {"id": "PR-CLOUDSPAN", "principles": ["P9"], "counterparty": "CloudSpan (2025)",
     "quote": "We can't do Europe — Europe is where we're growing.", "outcome": "Exclusivity narrowed to India + GCC"},
]
PRECEDENT_SOURCE = "negotiation_notes.md"

# --------------------------------------------------------------------------
# Intake context for the 15 drafts in the queue (FR-02: pre-filled from the
# tracker, confirmed by the seller). Deadlines live in tracker notes only.
# --------------------------------------------------------------------------

DEALS = {
    "harrington": {"name": "Harrington Health bundle", "client": "Harrington Health Systems Inc", "data_types": ["PHI"],
                   "signed_members": ["2026-08-20_harrington_health_mutual_nda.md"],
                   "related_signed": ["2025-10-06_atliq_intercompany_subcontractor_baa.md", "2025-10-06_carebridge_clinics_baa.md"]},
    "rheinwerk": {"name": "Rheinwerk project", "client": "Rheinwerk Analytics GmbH", "data_types": ["EU_PD"],
                  "signed_members": [], "related_signed": []},
    "lakeshore": {"name": "Lakeshore project", "client": "Lakeshore Grocers Inc", "data_types": [],
                  "signed_members": [], "related_signed": []},
    "sunrise": {"name": "Sunrise Foods", "client": "Sunrise Foods", "data_types": [],
                "signed_members": ["2025-04-18_sunrise_foods_msa.md"], "related_signed": []},
}

INTAKE = {
    "2026-09-10_harrington_health_msa_draft.md": dict(
        tracker_id="C-023", counterparty="Harrington Health Systems Inc", doc_type="MSA", side="supplier",
        service_region="USA", value=210000, currency="USD", deadline="2026-10-01", seller="Dhaval", deal="harrington",
        informal="no", informal_note=""),
    "2026-09-16_harrington_health_baa_draft.md": dict(
        tracker_id="C-046", counterparty="Harrington Health Systems Inc", doc_type="BAA", side="supplier",
        service_region="USA", value=None, currency="USD", deadline="2026-10-01", seller="Dhaval", deal="harrington",
        informal="no", informal_note=""),
    "2026-09-15_travelhub_services_agreement_draft.md": dict(
        tracker_id="C-024", counterparty="TravelHub", doc_type="Services agreement", side="supplier",
        service_region="United Arab Emirates", value=52000, currency="USD", deadline=None, seller="Karandeep", deal=None,
        informal="no", informal_note=""),
    "2026-09-18_gulf_crown_hotels_msa_draft.md": dict(
        tracker_id="C-025", counterparty="Gulf Crown Hotels & Resorts", doc_type="MSA", side="supplier",
        service_region="Saudi Arabia", value=140000, currency="USD", deadline="2026-10-10", seller="Bhavin", deal=None,
        informal="no", informal_note=""),
    "2026-09-19_lakeshore_grocers_msa_draft.md": dict(
        tracker_id="C-026", counterparty="Lakeshore Grocers Inc", doc_type="MSA + rate card", side="supplier",
        service_region="USA", value=64000, currency="USD", deadline="2026-10-03", seller="Jay", deal="lakeshore",
        informal="yes", informal_note="Jay gave a sharper rate to win it - $72/hr senior DE; Dhaval ok'd on a call (tracker C-026)."),
    "2026-09-21_blueorchid_hotels_pilot_agreement_draft.md": dict(
        tracker_id="C-027", counterparty="BlueOrchid Hotels", doc_type="Pilot agreement", side="supplier",
        service_region="India", value=38000, currency="USD", deadline="2026-10-05", seller="Jay", deal=None,
        informal="no", informal_note=""),
    "2026-09-23_rheinwerk_analytics_services_agreement_draft.md": dict(
        tracker_id="C-028", counterparty="Rheinwerk Analytics GmbH", doc_type="Services agreement", side="supplier",
        service_region="Germany", value=88000, currency="EUR", deadline="2026-10-15", seller="Bhavin", deal="rheinwerk",
        informal="no", informal_note=""),
    "2026-09-24_datavane_strategic_partnership_agreement_draft.md": dict(
        tracker_id="C-035", counterparty="Datavane Inc", doc_type="Partnership agreement", side="partner",
        service_region="India, GCC, Europe", value=None, currency="USD", deadline="2026-10-15", seller="Bhavin", deal=None,
        informal="no", informal_note=""),
    "2026-09-24_sunrise_foods_sow2_draft.md": dict(
        tracker_id="C-029", counterparty="Sunrise Foods", doc_type="SOW", side="supplier",
        service_region="India", value=45000, currency="USD", deadline="2026-10-08", seller="Dhaval", deal="sunrise",
        informal="no", informal_note=""),
    "2026-09-25_finserve_capital_mutual_nda_draft.md": dict(
        tracker_id="C-036", counterparty="FinServe Capital", doc_type="NDA", side="nda",
        service_region="India", value=None, currency="USD", deadline="2026-09-30", seller="Karandeep", deal=None,
        informal="no", informal_note=""),
    "2026-09-26_kriti_data_labs_subcontractor_agreement_draft.md": dict(
        tracker_id="C-037", counterparty="Kriti Data Labs", doc_type="Subcontractor agreement", side="buyer",
        service_region="India", value=840000, currency="INR", deadline="2026-10-05", seller="Pranav", deal="rheinwerk",
        informal="no", informal_note=""),
    "2026-09-27_daniel_ortiz_contractor_agreement_draft.md": dict(
        tracker_id="C-047", counterparty="Daniel Ortiz", doc_type="Contractor agreement", side="buyer",
        service_region="USA", value=None, currency="USD", deadline=None, seller="Dhaval", deal="harrington",
        informal="no", informal_note=""),
    "2026-09-27_daniel_ortiz_nda_draft.md": dict(
        tracker_id="C-048", counterparty="Daniel Ortiz", doc_type="NDA", side="nda",
        service_region="USA", value=None, currency="USD", deadline=None, seller="Dhaval", deal="harrington",
        informal="no", informal_note=""),
    "2026-09-27_loopmart_mutual_nda_draft.md": dict(
        tracker_id="C-038", counterparty="LoopMart", doc_type="NDA", side="nda",
        service_region="India", value=None, currency="USD", deadline=None, seller="Jay", deal=None,
        informal="no", informal_note=""),
    "2026-09-27_marcus_reed_contractor_agreement_draft.md": dict(
        tracker_id="C-040", counterparty="Marcus Reed", doc_type="Contractor agreement", side="buyer",
        service_region="USA", value=None, currency="USD", deadline="2026-10-01", seller="Jay", deal="lakeshore",
        informal="no", informal_note=""),
}

# Signed file -> tracker records it evidences (for the coverage line, FR-29).
SIGNED_FILE_TRACKER = {
    "2022-07-01_orbit_travels_msa_scanned.md": ["C-001"],
    "2024-08-01_crestline_retail_msa.md": ["C-002"],
    "2025-01-22_al_noor_mutual_nda.md": ["C-013"],
    "2025-01-22_paytrack_technologies_msa.md": ["C-005"],
    "2025-03-10_acme_retail_group_msa.md": ["C-006"],
    "2025-03-15_al_noor_hospitality_msa.md": ["C-007"],
    "2025-04-18_sunrise_foods_msa.md": ["C-008"],
    "2025-04-28_rohan_iyer_contractor_agreement.md": ["C-039"],
    "2025-06-20_northwind_logistics_msa.md": ["C-009", "C-010"],
    "2025-09-01_cloudspan_strategic_partnership_agreement.md": ["C-032"],
    "2025-10-06_atliq_intercompany_subcontractor_baa.md": ["C-044"],
    "2025-10-06_carebridge_clinics_baa.md": ["C-043"],
    "2025-11-28_brightwater_insurance_msa.md": ["C-014"],
    "2026-02-10_al_noor_waiver_letter.md": ["C-016"],
    "2026-07-16_meridian_healthcare_nda.md": ["C-020"],
    "2026-08-15_trustline_nbfc_msa.md": ["C-021"],
    "2026-08-20_harrington_health_mutual_nda.md": ["C-045"],
}

# --------------------------------------------------------------------------
# Promise Register back-fill (FR-25). Structured fields are what the register
# custodian confirms beside the source clause; anchors are verified verbatim.
# end_rule lets code compute end dates (PRD: "Must be exact").
# --------------------------------------------------------------------------

REGISTER_SEED = [
    dict(id="R-ALNOOR-NC", counterparty="Al Noor Hospitality Group", type="Non-compete",
         file="2025-03-15_al_noor_hospitality_msa.md", clauses="§12.1–12.3 (+ §1.9 GCC, §1.11 Hospitality Business, §1.14 Restricted Period)",
         entity="AtliQ Technologies Pvt Ltd", affiliates=True,
         activity="No data analytics, AI or revenue-management services to any Hospitality Business in the GCC",
         industries=["hospitality"], services=["analytics", "ai", "revenue management"], geographies=GCC,
         industry_definition="Owns, operates, manages or franchises hotels, resorts or serviced apartments - or provides distribution, revenue-management or guest-analytics services to them (§1.11)",
         start="2025-03-15", end_rule=("add_months", "2028-03-14", 18), end_note="Term to 14 Mar 2028 + 18-month Restricted Period",
         anchors=["neither it nor any of its Affiliates shall, during the Restricted Period, directly or indirectly, provide data analytics, artificial intelligence or revenue-management services to any Hospitality Business in the GCC",
                  "or that provides distribution, revenue-management or guest-analytics services to any such person, firm or entity",
                  "headquartered in, or the services relate to properties or operations located in, any state of the GCC, irrespective of where the services are performed",
                  "\"**Restricted Period**\" means the Term and the period of eighteen (18) months following the expiry or termination of this Agreement"],
         label="standard", confirmed=True),
    dict(id="R-ALNOOR-WAIVER", counterparty="Al Noor Hospitality Group", type="Waiver (narrowing)", parent="R-ALNOOR-NC",
         file="2026-02-10_al_noor_waiver_letter.md", clauses="¶2–3",
         entity="AtliQ Technologies Pvt Ltd", affiliates=False,
         activity="Consent only for the Seaside Hotels (Muscat) demand-forecasting SOW; excludes follow-ons, other GCC hospitality businesses and AtliQ's Affiliates",
         industries=["hospitality"], services=[], geographies=["Oman"], beneficiary="Seaside Hotels LLC",
         start="2026-02-10", end_rule=("fixed", "2026-08-31"), end_note="Seaside SOW ended 31 Aug 2026 (tracker C-017) - spent; any renewal needs new consent",
         anchors=["solely as described in the statement of work between the Supplier and Seaside dated February 2026",
                  "This consent is strictly limited to the Seaside SOW.",
                  "(b) any other Hospitality Business, whether in the Sultanate of Oman or elsewhere in the GCC; or (c) any Affiliate of the Supplier"],
         label="standard", confirmed=True, status_override="spent"),
    dict(id="R-ALNOOR-LD", counterparty="Al Noor Hospitality Group", type="Negotiated exception",
         file="2025-03-15_al_noor_hospitality_msa.md", clauses="§10.3",
         entity="AtliQ Technologies Pvt Ltd", affiliates=False,
         activity="LD 1%/week of milestone fee, capped at 10% of total fees - strategic exception, not a standard",
         industries=[], services=[], geographies=[],
         start="2025-03-15", end_rule=("fixed", "2028-03-14"), end_note="Term",
         anchors=["shall not exceed ten percent (10%) of the total Fees payable under this Agreement"],
         label="deliberate exception", confirmed=True),
    dict(id="R-CRESTLINE-MFN", counterparty="Crestline Retail Inc", type="Most-favoured pricing",
         file="2024-08-01_crestline_retail_msa.md", clauses="§6.4–6.5, Exhibit B",
         entity="AtliQ Inc", affiliates=True,
         activity="Rates no less favourable than any other customer for substantially similar services; lower rates apply retroactively with credits; annual audit",
         industries=["retail"], services=["data engineering", "bi"], geographies=["*"],
         rates={"Senior Data Engineer": 85, "Data Engineer": 62, "BI Developer": 58},
         start="2024-08-01", end_rule=("fixed", "2027-07-31"), end_note="Term to 31 Jul 2027",
         anchors=["no less favorable than those offered by Supplier or its Affiliates to any other customer for substantially similar services during the Term",
                  "such lower rates shall apply to Crestline retroactively from the date they were first offered to such other customer",
                  "| Senior Data Engineer | $85.00 |"],
         label="standard", confirmed=True),
    dict(id="R-CRESTLINE-DATA", counterparty="Crestline Retail Inc", type="Data location",
         file="2024-08-01_crestline_retail_msa.md", clauses="§13.3",
         entity="AtliQ Inc", affiliates=False,
         activity="No access to Crestline production data from outside the US without approval",
         industries=[], services=[], geographies=["USA"],
         start="2024-08-01", end_rule=("fixed", "2027-07-31"), end_note="Term",
         anchors=["Supplier shall not access Crestline production data from outside the United States without Crestline's prior written approval."],
         label="standard", confirmed=True),
    dict(id="R-CLOUDSPAN-EXCL", counterparty="CloudSpan Technologies", type="Exclusivity",
         file="2025-09-01_cloudspan_strategic_partnership_agreement.md", clauses="§7.1–7.4 (+ §1.10 Territory)",
         entity="AtliQ Technologies Pvt Ltd", affiliates=True,
         activity="No implementation, reseller or referral partnership with any competing cloud data-warehouse / lakehouse / unified-analytics platform in India or the GCC",
         industries=["cloud data platform"], services=["platform partnership"], geographies=["India"] + GCC,
         start="2025-09-01", end_rule=("fixed", "2028-08-31"), end_note="31 Aug 2028 (ends on termination; 90-day mutual termination for convenience, §14.2)",
         anchors=["during the Term Partner and its Affiliates shall not act as an implementation, reseller or referral partner for any Competing Platform in India or the GCC",
                  "\"**Competing Platform**\" means any cloud data-warehouse, lakehouse or unified analytics platform offered as a service.",
                  "Either Party may terminate this Agreement for convenience by giving not less than ninety (90) days' written notice to the other."],
         label="standard", confirmed=True),
    dict(id="R-CLOUDSPAN-CAP", counterparty="CloudSpan Technologies", type="Capacity commitment",
         file="2025-09-01_cloudspan_strategic_partnership_agreement.md", clauses="§3.1",
         entity="AtliQ Technologies Pvt Ltd", affiliates=False,
         activity="Maintain at least 4 CloudSpan-certified engineers",
         industries=[], services=[], geographies=[],
         start="2025-09-01", end_rule=("fixed", "2028-08-31"), end_note="Term",
         anchors=["not fewer than four (4) Certified Engineers"], label="standard", confirmed=True),
    dict(id="R-NORTHWIND-IP", counterparty="Northwind Logistics", type="IP assignment",
         file="2025-06-20_northwind_logistics_msa.md", clauses="§9.2 + SOW-1 S1.2",
         entity="AtliQ Technologies Pvt Ltd", affiliates=False,
         activity="All IP in Deliverables, including pre-existing materials incorporated (PipeKit), assigned to Northwind on payment",
         industries=[], services=[], geographies=["*"], assets=["PipeKit"],
         start="2025-06-20", end_rule=("permanent",), end_note="Permanent (assigned on payment)",
         anchors=["including any software, tools, frameworks, libraries and pre-existing materials incorporated into the Deliverables, shall vest in the Client absolutely upon payment",
                  "PipeKit will be configured and extended for the Client and incorporated into the delivered pipeline as its ingestion and orchestration layer."],
         label="accidental", confirmed=True),
    dict(id="R-NORTHWIND-LAW", counterparty="Northwind Logistics", type="Negotiated exception",
         file="2025-06-20_northwind_logistics_msa.md", clauses="§17",
         entity="AtliQ Technologies Pvt Ltd", affiliates=False,
         activity="English law, LCIA arbitration (deliberate: 'not worth losing the deal over')",
         industries=[], services=[], geographies=[],
         start="2025-06-20", end_rule=("fixed", "2028-06-19"), end_note="Term",
         anchors=["shall be governed by the law of England and Wales"], label="deliberate exception", confirmed=True),
    dict(id="R-BRIGHTWATER", counterparty="Brightwater Insurance Inc", type="Accidental exposure",
         file="2025-11-28_brightwater_insurance_msa.md", clauses="§9.1, §15.3, §20, §7.4",
         entity="AtliQ Inc", affiliates=False,
         activity="LD 1% of contract value per day, uncapped and outside the liability cap; English law, London courts; group-wide set-off",
         industries=[], services=[], geographies=[],
         start="2025-11-28", end_rule=("add_months", "2025-11-28", 18), end_note="18-month term",
         anchors=["one per cent (1%) of the Contract Value for each day or part day by which the relevant Key Date is missed",
                  "governed by and construed in accordance with the law of England and Wales"],
         label="accidental", confirmed=True),
    dict(id="R-ORBIT-NC", counterparty="Orbit Travels Pvt Ltd", type="Non-compete",
         file="2022-07-01_orbit_travels_msa_scanned.md", clauses="§6.1–6.2",
         entity="AtliQ Technologies Pvt Ltd", affiliates=False,
         activity="No travel-booking software for online travel agencies in India",
         industries=["online travel agency"], services=["travel-booking software"], geographies=["India"],
         start="2022-07-01", end_rule=("add_months", "2024-06-30", 12), end_note="30 Jun 2024 + 12 months",
         anchors=["it shall not develop, license or\nprovide travel-booking software to any online travel agency operating in India."],
         label="standard", confirmed=False, low_confidence=True),
    dict(id="R-ROHAN-IP", counterparty="Rohan Iyer", type="IP retained by freelancer",
         file="2025-04-28_rohan_iyer_contractor_agreement.md", clauses="§5.2–5.3",
         entity="AtliQ Technologies Pvt Ltd", affiliates=False,
         activity="Rohan owns the Acme dashboards' Work Product; AtliQ has a non-exclusive licence only (chain-of-title gap vs Acme §9.1)",
         industries=[], services=[], geographies=[],
         start="2025-04-28", end_rule=("permanent",), end_note="Perpetual licence",
         anchors=["The Contractor retains ownership of all intellectual property rights in the Work Product"],
         label="deliberate exception", confirmed=True),
    dict(id="R-CAREBRIDGE-BAA", counterparty="CareBridge Clinics Inc", type="Data location / scope",
         file="2025-10-06_atliq_intercompany_subcontractor_baa.md", clauses="IC-BAA §1.2, §3.1, Schedule 1 (+ CareBridge BAA §3.2, §9.1)",
         entity="AtliQ Inc / AtliQ Pvt Ltd", affiliates=False,
         activity="Pune (Pvt Ltd) may access de-identified data only, for the CareBridge engagement only. Breach liability cap 2x 12-month fees is a precedent.",
         industries=["healthcare"], services=[], geographies=["USA"], scope_client="CareBridge Clinics",
         start="2025-10-06", end_rule=("fixed", "2026-10-05"), end_note="Upstream CareBridge MSA expiry 5 Oct 2026 (tracker)",
         anchors=["\"**Engagement**\" means the CareBridge Engagement described in Schedule 1.",
                  "Subcontractor and its personnel shall access De-identified Data only."],
         label="standard", confirmed=True),
    dict(id="R-MERIDIAN", counterparty="Meridian Healthcare", type="One-way NDA + non-hire",
         file="2026-07-16_meridian_healthcare_nda.md", clauses="§2.1, §7.3",
         entity="AtliQ Technologies Pvt Ltd", affiliates=False,
         activity="Only AtliQ bound; 24-month ban on soliciting or engaging Meridian staff it met",
         industries=["healthcare"], services=[], geographies=["India"],
         start="2026-07-16", end_rule=("add_months", "2029-07-16", 24), end_note="3-year term + 24 months",
         anchors=["for a period of twenty-four (24) months thereafter, the Recipient shall not, directly or indirectly, solicit for employment or engagement"],
         label="accidental", confirmed=True),
    dict(id="R-HARRINGTON-NDA", counterparty="Harrington Health Systems Inc", type="Data handling condition",
         file="2026-08-20_harrington_health_mutual_nda.md", clauses="§2.3",
         entity="AtliQ Inc", affiliates=False,
         activity="PHI excluded; to be disclosed only after a BAA is signed",
         industries=["healthcare"], services=[], geographies=["USA"],
         start="2026-08-20", end_rule=("fixed", "2028-08-20"), end_note="Disclosure period",
         anchors=["shall be disclosed only after execution of a Business Associate Agreement between the Parties"],
         label="standard", confirmed=True),
    dict(id="R-PAYTRACK", counterparty="PayTrack Technologies", type="Data location / non-solicit",
         file="2025-01-22_paytrack_technologies_msa.md", clauses="§7.2, §10.2, §13.1",
         entity="AtliQ Technologies Pvt Ltd", affiliates=False,
         activity="Payment data stored only in India; mutual indemnity (precedent); 12-month employee non-solicit",
         industries=["financial services"], services=[], geographies=["India"],
         start="2025-01-22", end_rule=("fixed", "2027-01-21"), end_note="Term",
         anchors=["shall ensure that such data is stored only in India"], label="standard", confirmed=True),
    dict(id="R-TRUSTLINE", counterparty="Trustline NBFC", type="Data location / precedent",
         file="2026-08-15_trustline_nbfc_msa.md", clauses="§7, §13",
         entity="AtliQ Technologies Pvt Ltd", affiliates=False,
         activity="Data stored only in India; 6-hour incident report; LD 0.5%/week of milestone, cap 5%, client delays excluded (precedent)",
         industries=["financial services"], services=[], geographies=["India"],
         start="2026-08-15", end_rule=("fixed", "2027-08-14"), end_note="Term",
         anchors=["shall store Company Data only in India"], label="standard", confirmed=True),
]

# Signed files read with no restrictive covenant found (they still count toward coverage).
NO_COVENANT_FILES = {
    "2025-01-22_al_noor_mutual_nda.md": "Mutual NDA - no restrictive covenant found",
    "2025-03-10_acme_retail_group_msa.md": "Standard terms - LD precedent 0.5%/week of milestone, cap 5%",
    "2025-04-18_sunrise_foods_msa.md": "Standard terms - no restrictive covenant or pricing promise found",
    "2025-10-06_carebridge_clinics_baa.md": "Linked to R-CAREBRIDGE-BAA",
}

BANNED_PHRASES = ["safe to sign", "no conflict"]
DISCLAIMER = "Not legal advice. A person decides."
