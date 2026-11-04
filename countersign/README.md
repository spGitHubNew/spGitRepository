# CounterSign — AtliQ Contract Risk Analyzer (prototype)

A pre-signature contract-review copilot plus a **Promise Register**, built from
`PRD - AtliQ Contract Risk Analyzer.docx` to address the root cause found in
`Problem_Discovery_and_User_Research.xlsx`: *AtliQ has no institutional memory of what
it has signed*. The deciding risk usually sits in another file (a signed contract, a waiver, a
meeting note, the entity sheet), so CounterSign reads every clause **and** checks the deal
against what AtliQ has already promised.

> **Not legal advice. A person decides.** CounterSign never signs, approves, sends or
> negotiates anything, and never says "safe to sign" or that a deal is free of past-promise conflicts.

## Run it

Requires only Python 3.10+ (standard library; nothing to install).

```bash
python app.py
```

Open http://localhost:8765 (on Windows you can double-click `run.bat`). Use the role
picker (top right) to see the product as Karandeep (reviewer), a seller (Bhavin, Dhaval,
Jay), Jay as register custodian, or Pranav (CTO).

Run the golden-set evals (PRD §11) from the command line or the **Evals** page:

```bash
python -m evals.run_evals
```

Current result: **21/21 pass**. That covers the S1–S15 scenarios, groundedness, banned phrases, coverage line, N-of-N clauses, rule correctness and latency (about 0.1 s per contract).

### Optional AI second pass
The review is complete without AI (the PRD is rules-first). To add a Claude second pass
that proposes extra findings and explains "possible" conflicts, set `COUNTERSIGN_AI=1`
and Anthropic credentials (`ANTHROPIC_API_KEY` or an `ant auth login` profile).
The model defaults to `claude-opus-5-5`; override it with `COUNTERSIGN_MODEL`. Every AI quote is
verified against the source like any rule finding. Contract text is passed as data and is
never followed as instructions.

## What it does (PRD traceability)

| PRD | Where |
|---|---|
| F3 / FR-06–12 Clause review vs P1–P11, Serious first, verified quotes, exposure in code | `engine/checks.py`, `engine/review.py` |
| F4 / FR-13–15 Fairness both ways, hidden NDA covenants, AtliQ's own paper (P10) | `checks.py` (lens per side of the table), Fairness tab |
| F5 / FR-16 Entity, law, forum, invoicing rule table (no AI) | `engine/rules.py::check_entity` |
| F6 / FR-17–20 Bundle, flow-downs, facts table, cross-document contradictions | `engine/rules.py::check_bundle` |
| F1 / FR-21–26 Promise Register: back-fill of the 17 signed files, verified anchors, computed end dates, waivers linked to parents, custodian confirmation, extraction at signature | `engine/knowledge.py::REGISTER_SEED`, `engine/register.py` |
| F2 / FR-27–32 Conflict check incl. Affiliates and waiver limits, "Possible – confirm" with the settling question, coverage line, lead-stage search | `engine/conflicts.py`, Register page |
| F7 / FR-33 Precedents from `negotiation_notes.md`, labelled unreviewed | `knowledge.py::PRECEDENTS` |
| FR-34–41 Dispositions (reason required to accept a Serious item), ready-to-sign gate, counsel pack (prepared, never sent), role views, append-only audit log, refusal of legal-advice questions, "missed anything?", sortable queue | `app.py`, `static/app.js`, `engine/store.py` |
| FR-01–05 Upload PDF / Word / text, pre-filled deal context, required "agreed outside the document?" question, PHI upload block | `engine/ingest.py`, New contract page |
| §10 Guardrails GR-01…GR-10 | enforced in code: `review.py::guard`, `app.py` gates, `text.py::verify_quote` |
| §12 North Star: Informed Decision Rate | Evals page (`/api/metrics`) |

## What V1 shows on today's queue (28 Sep 2026)

| Draft | Headline output |
|---|---|
| Harrington MSA + BAA | Uncapped LD at **$4,200/calendar day**, unlimited liability, negligence indemnity, 7-day termination without WIP pay, pre-existing IP assigned, 90-day payment, $5M cyber vs $1M held; bundle: Ortiz subcontractor BAA missing, intercompany BAA covers CareBridge only, Pvt Ltd cannot be a BAA subcontractor; **act now: PHI in Pune before any BAA** |
| Gulf Crown | Conflict with Al Noor §12 (binds Affiliates, runs to **14 Sep 2029**; Seaside waiver spent and doesn't cover); warranty 9.1(d) untrue; 10% LD flagged as the Al Noor exception; Arabic text prevails |
| TravelHub | Wrong entity (Inc for a UAE client) and invoicing from Pvt Ltd GSTIN; possible Al Noor conflict, with the settling question about hotel distribution |
| BlueOrchid | Looks clean; possible Al Noor conflict via Dubai Business Bay, Dubai Marina, Muscat Qurum |
| Lakeshore | Crestline MFN breached on all three roles ($72/$55/$50 vs $85/$62/$58, retroactive credits); SIAC forum for AtliQ Inc |
| Rheinwerk | PipeKit ownership vs Northwind §9.2; DPA Annex 3 missing; German-law liability not rated Serious; Kriti flow-down gaps |
| Datavane | CloudSpan exclusivity conflict; one-sided termination; uncapped indemnity; 24-month account ban binding Affiliates |
| FinServe "Mutual" NDA | One-way; residuals; perpetual; 12-month non-compete that would bite Trustline, PayTrack, FinEdge |
| Kriti; Marcus Reed | AtliQ's own paper harsher than AtliQ accepts (PixelCraft precedent); Marcus on the India template and the wrong entity for a US contractor |
| Sunrise SOW-2; LoopMart; Ortiz NDA | "No Serious findings from the checks we ran. This is not a clearance." |

## Design notes

- **Rules first, AI only where the text is unstructured** (PRD §5). Entity, bundle, dates and
  arithmetic are deterministic. Clause classification uses transparent patterns plus party-role
  detection (who is the obligor), so every finding is explainable and reproducible.
- **Quotes are verified, not trusted.** Each displayed quote is string-matched against its source
  file. Anything unverifiable shows as "Not sure – please cross-check".
- **Definitions travel with clauses.** Al Noor's "hotel" and "GCC" live in §1.9/§1.11, not §12.
- **Coverage is always stated** ("Checked 18 of 29 signed records; 11 not on file; 1 low-confidence scan").
- **Deadlines never change severity.** Eval S14 checks this.

## Dataset additions / assumptions
- No new contracts were added. The register back-fill (`knowledge.py::REGISTER_SEED`) holds the
  structured fields a custodian would confirm. Every anchor quote is verified against its signed file
  at runtime, and the Orbit scan is left unconfirmed (low confidence).
- Deal context for the 15 drafts (side of the table, region, value, deadline, bundle) is pre-filled
  from `contract_tracker.csv` notes, as the intake step would capture it.
- The facts table holds only facts stated in the dataset (e.g. cyber cover $1M from the 27 Sep huddle).
- Evals S13 (Brightwater back-test) and S15 (injected instruction) build their test documents at runtime.
- Role switching stands in for SSO/RBAC. Data is stored locally in `data/` (state + append-only audit log).
