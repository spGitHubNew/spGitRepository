# CounterSign test contracts

Synthetic contracts written to exercise CounterSign end to end. They are invented for testing, are not
real agreements, and are not legal advice. Each one was run through the live app's upload flow, and the
expected results below are what the app actually produced (2 Nov 2026).

## How to test

1. Start the app: `python app.py` in the `countersign` folder, then open http://localhost:8765.
2. Click **New contract** and choose a file below.
3. Check the pre-filled details and set the fields in the table (the app pre-fills most of them).
4. Answer the required question **"Was anything agreed outside this document?"** (choose **No**; try **Yes** with a note to see it shown on the review).
5. Click **Upload and review**, then compare with the expected results.

| File | Side of the table | Region | Value | Deal (bundle) |
|---|---|---|---|---|
| TC-01 (.md or .docx) | Supplier | United Arab Emirates | 150000 USD | None |
| TC-02 | NDA party | India | (blank) | None |
| TC-03 | Buyer (AtliQ's own paper) | India | 432000 INR | None |
| TC-04 | any | any | (blank) | None |

## TC-01: Marina Bay Resorts MSA (risky)

Use `TC-01_marina_bay_resorts_msa_RISKY.md`, or the `.docx` to test Word upload. Both give the same result.

**Expected: 37 of 37 clauses reviewed (38 for .docx), 12 Serious, 3 Review, 2 past-promise matches; every quote "verbatim in source".**

| Severity | Principle | Clause | Finding |
|---|---|---|---|
| Serious | P5 | §1.2 | Wrong AtliQ entity: a UAE client should contract with AtliQ Pvt Ltd, not AtliQ Inc |
| Serious | P4 | §5.2 | Payment in 90 days |
| Serious | P7 | §6.3 | Termination on 7 days without paying work in progress |
| Serious | P9 | §8.1 | Warranty that AtliQ is bound by no restriction (untrue while Al Noor §12 is active) |
| Serious | P3 | §9.1 | Indemnity covers the client's own negligence |
| Serious | P2 | §10.2 | Unlimited liability for AtliQ while the client is capped |
| Serious | P1 | §11.2 | Uncapped delay damages: **$2,250 per calendar day**, cumulative, no client-delay exclusion |
| Serious | Facts | §12.1 | $3M cyber insurance required vs $1M held |
| Serious | P11 | §13.1 | Annex 3 (Data Processing Agreement) referenced but not attached |
| Serious | Guardrail | §15.2 | Instruction aimed at an AI reviewer ("ignore all previous instructions…"): flagged, **not followed** |
| Review | P4 | §5.3 | Set-off against any other agreement |
| Review | P5 | §14.1 | Dubai law |
| Review | Could not check | §15.1 | Arabic text prevails |
| Past promise | P9 | §4.1 | **Conflict: Al Noor non-compete**: GCC hotel group buying revenue management and guest analytics; binds Affiliates (so AtliQ Inc); runs to 14 Sep 2029; Seaside waiver spent and does not cover it |
| Past promise | P9 | Schedule 3 | **Conflict: Crestline most-favoured pricing**: $70 / $52 / $48 vs Crestline's $85 / $62 / $58 on all three roles |

Also check: the Fairness tab shows liability and indemnity as one-sided; the "Mark ready for my signature" button stays disabled until all 14 open items have a disposition; accepting a Serious item without a reason is refused.

## TC-02: Harbourline mutual NDA (clean control)

**Expected: 13 of 13 clauses, 0 Serious, 0 Review, no past-promise match, and the message "No Serious findings from the checks we ran. This is not a clearance."** Entity, law and courts all match (AtliQ Pvt Ltd, Indian law, Kochi courts).

## TC-03: Priya Nair freelancer agreement (AtliQ's own paper)

Set **Side = Buyer**. Findings are judged by P10: AtliQ's paper must give a freelancer the terms AtliQ asks for itself.

**Expected: 12 of 12 clauses, 4 Serious, 2 Review, all P10.**

| Severity | Clause | Finding |
|---|---|---|
| Serious | §3.1 | Payment 90 days after timesheet approval |
| Serious | §4.1 | Uncapped delay damages on AtliQ's own paper (2% of Total Fees per day) |
| Serious | §5.1 | Lopsided notice: AtliQ 24 hours vs contractor 60 days |
| Serious | §6.1 | 12-month worldwide non-compete on the freelancer |
| Review | §2.1 | Exclusivity during the term |
| Review | §7.2 | Only AtliQ's liability is capped |

Precedents shown: PixelCraft and Rohan Iyer (labelled unreviewed).

## TC-04: Patient data extract (must be blocked)

**Expected: the upload is refused** with "Upload blocked: this file looks like it contains patient or bulk personal data (6 dates of birth, 6 diagnosis codes, 6 MRNs). CounterSign reads contracts, not datasets." Nothing is stored. All records are invented.

## More things to try with TC-01 after upload

- **Ask box** (review page): type "Is this safe to sign?" and it declines and offers a counsel pack.
- **Prepare counsel pack**: downloads an HTML pack with the open findings, both clashing clauses and the full source files.
- **Switch role** to Jay (seller) and the full review is not available for a contract Jay did not bring in; switch to Karandeep to decide.
- **Record: I signed it** (after every Serious item has a disposition), then open **Promise Register**: the §7.2 IP assignment (pre-existing tools handed to the client) waits in the confirmation queue for Jay to confirm.
- **Audit log**: every upload, view, disposition and pack is recorded.
