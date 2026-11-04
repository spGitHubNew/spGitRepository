"""Clause review against AtliQ's principles (FR-06 - FR-15).

Each detector reads the segmented clauses, works out which party carries the
burden, computes exposure in code (FR-10) and emits findings that quote the
clause verbatim. AtliQ's side of the table decides the lens: on client paper we
protect AtliQ (P1-P9); on AtliQ's own paper we apply AtliQ's supplier-side
positions to the counterparty (P10).
"""

import hashlib
import re

from .knowledge import FACTS, PRECEDENTS
from .text import best_quote, money, parse_days, sentences, side_of


def fid(*parts):
    return "F-" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8]


def precedents_for(principle):
    return [p for p in PRECEDENTS if principle in p["principles"]][:3]


class Ctx:
    def __init__(self, doc):
        self.doc = doc
        self.clauses = doc["clauses"]
        self.labels = doc["labels"]
        self.side = doc["side"]          # supplier | buyer | partner | nda
        self.value = doc.get("value")
        self.currency = doc.get("currency") or "USD"
        self.findings = []
        self.passed = []
        self.could_not_check = []
        self.fair = []                   # (type, side, quote, ref)

    def article(self, clause):
        return "\n".join(c["text"] for c in self.clauses if c["heading"] == clause["heading"])

    def lens(self, burdened):
        """Return the principle family to apply for a burden on `burdened`, or None if it favours AtliQ."""
        if burdened == "atliq":
            return "own"
        if burdened == "other" and self.side == "buyer":
            return "p10"
        return None

    def add(self, key, severity, principle, title, reason, clause, pattern, exposure=None, category="Clause review",
            quote=None):
        q = quote or best_quote(clause["text"], pattern)
        f = {"id": fid(self.doc["file"], key, clause["ref"]), "key": key, "severity": severity,
             "principle": principle, "title": title, "reason": reason, "clause_ref": clause["ref"],
             "clause_title": clause.get("title") or clause.get("heading"), "quote": q, "exposure": exposure,
             "category": category, "precedents": precedents_for(principle.split()[0]), "origin": "rule",
             "definitions": clause.get("definitions", [])[:6]}
        self.findings.append(f)
        return f


PCT = r"(\d+(?:\.\d+)?)\s*%"


def _pct(s):
    m = re.search(PCT, s)
    return float(m.group(1)) if m else None


# ------------------------------------------------------------------ P1 delay damages

LD_RX = re.compile(r"liquidated damages|contractual penalty|Vertragsstrafe|service credit|delay penalt", re.I)
PERIOD_RX = re.compile(r"calendar day|each day|per day|day or part day|week", re.I)


def check_delay_damages(ctx):
    for c in ctx.clauses:
        if not LD_RX.search(c["text"]) and not re.search(r"delay", c["heading"], re.I):
            continue
        for s in sentences(c["text"]):
            if not (re.search(PCT, s) and PERIOD_RX.search(s)) or re.search(r"interest", s, re.I):
                continue
            if not (LD_RX.search(s) or re.search(r"shall pay|entitled to|may assess|may claim", s, re.I)):
                continue
            burdened = side_of(s, ctx.labels)
            lens = ctx.lens(burdened)
            rate = _pct(s)
            per = "day" if re.search(r"day", PERIOD_RX.search(s).group(0), re.I) else "week"
            milestone_base = bool(re.search(r"Milestone Fee|affected Milestone|relevant Milestone|delayed Milestone", s))
            base_label = "the affected milestone fee" if milestone_base else (
                "Total Contract Value" if "Total Contract Value" in s else
                "Total Fees" if "Total Fees" in s else "the contract value")
            art = ctx.article(c)
            capm = re.search(r"(?:not exceed|maximum of|up to a maximum of|capped at)\s+[^.%]*?\(?" + PCT, art, re.I)
            cap = float(capm.group(1)) if capm else None
            cap_on_milestone = bool(capm and re.search(r"that Milestone|of that Milestone|Milestone Fee of that", art[capm.start():capm.end() + 40]))
            other = "|".join(re.escape(l) for l in ctx.labels["other"]) or "Client"
            mine = "|".join(re.escape(l) for l in ctx.labels["atliq"])
            excl = bool(re.search(r"(caused by|attributable to|delay caused by)\s+(the\s+)?(" + other + r"|Client|Company|Customer)\b", art)
                        or re.search(r"(reasons|causes)\s+(solely\s+)?attributable to\s+(the\s+)?(" + mine + r")\b", art)
                        or re.search(r"for reasons for which it is responsible", art))
            cumulative = bool(re.search(r"in addition to and not in lieu|in addition to any other right", art, re.I))

            exp = {"rate": f"{rate:g}% of {base_label} per {per}"}
            if ctx.value and not milestone_base:
                per_amt = ctx.value * rate / 100
                exp["per_period"] = f"{money(per_amt, ctx.currency)} per {'calendar day' if per == 'day' else 'week'}"
                exp["to_100pct"] = f"{100 / rate:g} {per}s to reach 100% of contract value"
                if cap:
                    exp["cap"] = f"{cap:g}% = {money(ctx.value * cap / 100, ctx.currency)} (reached after {cap / rate:g} {per}s)"
            if cap and "cap" not in exp:
                exp["cap"] = f"{cap:g}% of {'that milestone fee' if cap_on_milestone else 'total fees'}"
            exp["cap_status"] = "no cap" if cap is None else "capped"
            exp["client_delay_excluded"] = "yes" if excl else "no"
            if cumulative:
                exp["cumulative"] = "in addition to actual damages"

            if lens is None:
                ctx.fair.append(("Delay damages", burdened or "both", s, c["ref"]))
                continue
            ctx.fair.append(("Delay damages", burdened, s, c["ref"]))
            principle = "P1" if lens == "own" else "P10"
            who = "AtliQ" if lens == "own" else "the vendor"
            bits = [exp["rate"]]
            if cap is None:
                bits.append("no cap")
            if cumulative:
                bits.append("cumulative with actual damages")
            if not excl:
                bits.append("no exclusion for delay caused by the other side")
            if cap is None:
                sev, title = "Serious", "Uncapped delay damages" + (" on AtliQ's own paper" if lens == "p10" else "")
            elif not milestone_base and (cap > 5 or not excl):
                sev, title = ("Serious" if not excl else "Review"), "Delay damages above AtliQ's position"
                bits.append(f"cap {cap:g}% of total value (precedent: 5% of the affected milestone)")
            elif not excl:
                sev, title = "Review", "Delay damages apply even when the other side causes the delay"
            elif rate > 0.5 or (cap and cap > 5):
                sev, title = "Review", "Delay damages above the 0.5%/week precedent"
            else:
                ctx.passed.append(f"Delay damages {c['ref']}: {exp['rate']}, capped, client-caused delay excluded - within P1 precedent")
                continue
            reason = f"{who.capitalize()} pays " + "; ".join(bits) + "."
            if cap == 10:
                reason += " The 10% cap matches the Al Noor deal, which was logged as a one-off exception, not AtliQ's standard."
            if lens == "p10":
                reason += " AtliQ would not accept this as a supplier (PixelCraft precedent)."
            ctx.add("ld", sev, principle, title, reason, c, PCT, exposure=exp)


# ------------------------------------------------------------------ P2 liability

UNLIM = re.compile(r"NOTHING IN THIS AGREEMENT SHALL LIMIT|shall not be subject to any limitation|not subject to any limitation or exclusion|without limitation for all damages|unlimited liability|liable without limitation", re.I)
CARVE = re.compile(r"intentionally|gross negligence|injury to life|Product Liability|wilful misconduct|fraud", re.I)
CAP = re.compile(r"liabilit[^.]{0,160}shall not exceed|shall not exceed[^.]{0,80}liabilit", re.I)


def check_liability(ctx):
    caps = {"atliq": [], "other": [], "both": []}
    unlimited = {"atliq": None, "other": None}
    for c in ctx.clauses:
        for s in sentences(c["text"]):
            if UNLIM.search(s):
                who = side_of(s, ctx.labels)
                if who is None and re.search(r"\bThe Parties\b|Each Party|either Party", s, re.I):
                    if CARVE.search(s) and not re.search(r"any losses|all damages", s, re.I):
                        ctx.passed.append(f"Liability {c['ref']}: unlimited only for intent, gross negligence or injury - a standard carve-out, not rated Serious")
                        ctx.fair.append(("Liability", "both", s, c["ref"]))
                        continue
                if who in unlimited and unlimited[who] is None:
                    unlimited[who] = (c, s)
                ctx.fair.append(("Liability", who or "both", s, c["ref"]))
            elif CAP.search(s):
                who = side_of(s, ctx.labels)
                if re.search(r"^(EACH PARTY|Each Party|Each party|Neither Party|NEITHER PARTY)", s):
                    who = "both"
                caps.setdefault(who or "both", []).append((c, s))
                ctx.fair.append(("Liability", who or "both", s, c["ref"]))
                mult = re.search(r"\((\d+)%\) of the Contract Value", s)
                if who == "atliq" and mult and int(mult.group(1)) > 100:
                    ctx.add("liab-mult", "Review", "P2", "Liability cap above 1x fees",
                            f"AtliQ's cap is {int(mult.group(1)) / 100:g}x the contract value (checklist: 1x fees).", c, r"shall not exceed")

    for who, hit in unlimited.items():
        if not hit:
            continue
        lens = ctx.lens(who)
        if lens is None:
            continue
        c, s = hit
        other_cap = caps["other"] if who == "atliq" else caps["atliq"]
        reason = ("AtliQ's liability is unlimited" if lens == "own" else "The vendor's liability is unlimited")
        if other_cap:
            oc = other_cap[0][1]
            absolute = re.search(r"(USD|\$)\s?[\d,]+|TEN THOUSAND", oc)
            reason += f", while the other side's liability is capped ({'a fixed USD amount' if absolute else 'at fees'})"
        reason += "; " + ("checklist: 1x fees, never unlimited (Kessler walk-away)." if lens == "own"
                          else "AtliQ itself would walk away from this (Kessler; PixelCraft got a mutual cap).")
        ctx.add("liab-unlimited", "Serious", "P2" if lens == "own" else "P10",
                "Unlimited liability" + (" on AtliQ's own paper" if lens == "p10" else ""), reason, c, UNLIM,
                exposure={"liability": "unlimited", "other side": "capped" if other_cap else "-"})

    # one-way cap on AtliQ's own paper (AtliQ capped, vendor not)
    if ctx.side == "buyer" and caps["atliq"] and not caps["other"] and not caps["both"] and not unlimited["other"]:
        c, s = caps["atliq"][0]
        ctx.add("liab-oneway", "Review", "P10", "Only AtliQ's liability is capped",
                "AtliQ caps its own liability but gives the counterparty no cap; Rohan Iyer and PixelCraft got a mutual cap.",
                c, CAP)


# ------------------------------------------------------------------ P3 indemnity

NEG = re.compile(r"regardless of whether such Losses are caused in whole or in part by the negligence|arising from the negligence of|caused in whole or in part by the negligence of", re.I)


def check_indemnity(ctx):
    broad = {"atliq": None, "other": None}
    narrow = {"atliq": False, "other": False}
    flagged = False
    for c in ctx.clauses:
        for s in sentences(c["text"]):
            if not re.search(r"indemnif", s, re.I):
                continue
            who = side_of(s, ctx.labels)
            if re.match(r"(Each Party|Each party)", s):
                who = "both"
            ctx.fair.append(("Indemnity", who or "both", s, c["ref"]))
            if NEG.search(s):
                lens = ctx.lens(who)
                if lens:
                    flagged = True
                    ctx.add("indem-neg", "Serious", "P3" if lens == "own" else "P10",
                            "Indemnity covers the other side's own negligence",
                            ("AtliQ would indemnify" if lens == "own" else "The vendor must indemnify") +
                            " losses even where they are caused by the indemnified party's own negligence. Checklist: 'we don't cover their mistakes' (PayTrack precedent).",
                            c, NEG)
            if (re.search(r"any and all Losses", s, re.I) or (re.search(r"all losses", s, re.I) and not re.search(r"infring", s, re.I))) and who in broad:
                broad[who] = broad[who] or (c, s)
            elif who in narrow:
                narrow[who] = True
    if not flagged and broad["atliq"] and not broad["other"] and ctx.lens("atliq") and "nda" not in ctx.doc["doc_type"].lower():
        c, s = broad["atliq"]
        ctx.add("indem-oneway", "Review", "P3", "One-way broad indemnity",
                "AtliQ indemnifies for any and all losses arising from its services, while the other side's indemnity is narrow or absent.",
                c, r"any and all Losses|all losses")


# ------------------------------------------------------------------ P4 payment

def check_payment(ctx):
    worst = None
    for c in ctx.clauses:
        for s in sentences(c["text"]):
            if re.search(r"set off|set-off", s, re.I) and re.search(r"any other agreement|any member of", s, re.I):
                if ctx.lens("atliq") == "own" or ctx.side != "buyer":
                    ctx.add("setoff", "Review", "P4", "Set-off across other contracts",
                            "The client may withhold money owed under this contract against amounts under any other agreement.", c,
                            r"set off|set-off")
                continue
            pww = re.search(r"conditional upon[^.]*receipt of payment|pay-when-paid|receives? payment from", s, re.I)
            if not (re.search(r"\bpa(y|id|yment)\b", s, re.I) and (re.search(r"invoice|receipt|approval|quarter", s, re.I) or pww)):
                continue
            days = parse_days(s)
            if days is None and not pww:
                continue
            payer = side_of(s, ctx.labels)
            if payer is None:
                payer = "atliq" if ctx.side == "buyer" else "other"
            if re.search(r"Invoices not submitted|shall be deemed waived|remit", s, re.I):
                continue
            payee = "other" if payer == "atliq" else "atliq"
            lens = "own" if payee == "atliq" else ("p10" if ctx.side == "buyer" else None)
            ctx.fair.append(("Payment", payer, s, c["ref"]))
            if lens is None:
                continue
            sev = None
            if pww and lens == "p10":
                sev = "Serious"
            elif days and days >= 90:
                sev = "Serious"
            elif days and days > 45:
                sev = "Review"
            elif pww:
                sev = "Review"
            if sev and (worst is None or (sev == "Serious" and worst[0] != "Serious")):
                worst = (sev, lens, c, s, days, bool(pww))
    if worst:
        sev, lens, c, s, days, pww = worst
        reason = (f"Payment {days} days" if days else "Payment timing") + (", conditional on the end client paying first" if pww else "") + \
                 ". Checklist: 30 days, 45 max (Trustline settled at 45)."
        if lens == "p10":
            reason += " AtliQ's own paper should give vendors what AtliQ asks for (PixelCraft: 30 days)."
        ctx.add("payment", sev, "P4" if lens == "own" else "P10",
                "Pay-when-paid" if pww else f"Payment terms {days} days", reason, c,
                r"conditional upon|within|days", exposure={"payment_days": days, "pay_when_paid": "yes" if pww else "no"})
    # currency / bank-charge burden on individual contractors (own paper)
    if ctx.side == "buyer":
        for c in ctx.clauses:
            if re.search(r"exchange rate determined by the Company at its discretion", c["text"]):
                ctx.add("fx", "Review", "P10", "Contractor bears FX and bank charges",
                        "USD fees paid in INR at a rate AtliQ chooses, with bank charges on the contractor.", c,
                        r"exchange rate determined")


# ------------------------------------------------------------------ P7 termination

def check_termination(ctx):
    tfc = {}
    denied = {}
    for c in ctx.clauses:
        for s in sentences(c["text"]):
            if re.search(r"may not terminate this Agreement for convenience", s, re.I):
                denied[side_of(s, ctx.labels)] = (c, s)
                ctx.fair.append(("Termination for convenience", side_of(s, ctx.labels), s, c["ref"]))
                continue
            if not (re.search(r"terminat", s, re.I) and re.search(r"convenience|for any reason|at any time|hours' written notice|by giving", s, re.I)):
                continue
            if re.search(r"breach|insolvent|material", s, re.I) and not re.search(r"convenience|any reason", s, re.I):
                continue
            who = side_of(s, ctx.labels)
            if re.match(r"(Either Party|Either party|either Party)", s):
                who = "both"
            hours = re.search(r"\((\d+)\) hours", s)
            notice_days = (int(hours.group(1)) / 24) if hours else parse_days(s)
            tfc[who] = (c, s, notice_days)
            ctx.fair.append(("Termination for convenience", who or "both", s, c["ref"]))
            art = c["text"]
            if re.search(r"no obligation to pay for work in progress", art, re.I):
                lens = "own" if who == "other" else ("p10" if who == "atliq" and ctx.side == "buyer" else None)
                if lens:
                    ctx.add("tfc-wip", "Serious", "P7" if lens == "own" else "P10",
                            f"Termination on {notice_days:g} days without paying work in progress",
                            ("The client" if lens == "own" else "AtliQ") + f" may terminate for any reason on {notice_days:g} days' notice and pay only for accepted deliverables - work in progress, demobilisation and committed costs are unpaid.",
                            c, r"no obligation to pay|terminate")
            elif re.search(r"performed and accepted", s) and who == "other" and ctx.side != "buyer":
                ctx.add("tfc-accepted", "Review", "P7", "Only accepted work is paid on termination",
                        "On termination for convenience the client pays for services 'performed and accepted' - work in progress may go unpaid.",
                        c, r"performed and accepted")
    if "atliq" in denied and ("other" in tfc):
        c, s = denied["atliq"]
        oc, os_, od = tfc["other"]
        ctx.add("tfc-oneway", "Serious", "FR-13 mutuality", "One-sided termination rights",
                f"The other side may terminate on {od:g} days' notice; AtliQ cannot terminate for convenience at all during the initial term.",
                c, r"may not terminate")
    if ctx.side == "buyer" and "atliq" in tfc and "other" in tfc:
        a, o = tfc["atliq"][2], tfc["other"][2]
        if a is not None and o is not None and o >= 4 * max(a, 1 / 24):
            c, s, _ = tfc["atliq"]
            ctx.add("tfc-asym", "Serious", "P10", "Lopsided notice periods",
                    f"AtliQ may terminate on {a * 24:g} hours' notice but the contractor needs {o:g} days." if a < 1 else
                    f"AtliQ may terminate on {a:g} days' notice but the contractor needs {o:g} days.", c, r"terminate")


# ------------------------------------------------------------------ P6 IP

def check_ip(ctx):
    for c in ctx.clauses:
        for s in sentences(c["text"]):
            if re.search(r"Pre-Existing Materials incorporated|pre-existing materials incorporated", s, re.I) and re.search(r"assign|vest", s, re.I):
                who = side_of(s, ctx.labels)
                if ctx.lens(who) == "own" or who is None:
                    ctx.add("ip-preexisting", "Serious", "P6", "AtliQ's pre-existing tools assigned to the client",
                            "Ownership of AtliQ's pre-existing materials (tools, libraries, accelerators) incorporated in a deliverable passes to the client. Checklist: 'we keep our own stuff'.",
                            c, r"Pre-Existing Materials|pre-existing materials")
            m = re.search(r"warrants that it is the sole owner of all intellectual property rights in (\w+)", s)
            if m and side_of(s, ctx.labels) == "atliq":
                ctx.add("ip-warranty", "Review", "P6", f"Ownership warranty for {m.group(1)}",
                        f"AtliQ warrants sole ownership of {m.group(1)} and grants a broad licence. Check chain of title against the Promise Register before signing.",
                        c, r"sole owner")
            if re.search(r"perpetual, irrevocable, royalty-free licence to use any feedback, connectors, templates or implementation accelerators", s):
                ctx.add("ip-accelerators", "Minor", "P6", "Licence to AtliQ accelerators",
                        "Anything AtliQ submits to the partner marketplace is licensed to the partner perpetually and irrevocably.", c,
                        r"accelerators")


# ------------------------------------------------------------------ restrictive covenants (P9 new promises, P8, P10)

NONCOMP = re.compile(r"shall not[^.]{0,220}?(provide|act as|solicit, market to|develop, license)[^.]{0,260}?(Competitor|Competing Platform|Datavane Account|Hospitality Business|in competition with|online travel agency)", re.I)


def check_restrictive(ctx):
    for c in ctx.clauses:
        for s in sentences(c["text"]):
            if NONCOMP.search(s):
                who = side_of(s, ctx.labels)
                months = re.search(r"\((\d+)\) months", s)
                span = f"{months.group(1)} months after the term" if months else "the term"
                affiliates = bool(re.search(r"Affiliates", s))
                ctx.fair.append(("Restrictive covenants", who or "both", s, c["ref"]))
                if who == "atliq":
                    ctx.add("new-restriction", "Serious", "P9", "New restrictive covenant on AtliQ" + (" and its Affiliates" if affiliates else ""),
                            f"Signing creates a new restriction running for {span}. If signed it must join the Promise Register; it is matched against existing clients below.",
                            c, NONCOMP, category="Restrictive covenant")
                elif who == "other" and ctx.side == "buyer":
                    ctx.add("p10-noncompete", "Serious", "P10", "Non-compete imposed on the contractor",
                            f"The contractor may not work for anyone 'in competition' for {span}" + (", worldwide" if re.search(r"anywhere in the world|worldwide", s) else "") +
                            ". Rohan Iyer and Daniel Ortiz agreements carry no non-compete.", c, NONCOMP, category="Restrictive covenant")
            elif re.search(r"devote his professional working time exclusively|exclusively to the Company", s) and ctx.side == "buyer":
                ctx.add("p10-exclusive", "Review", "P10", "Exclusivity during the term",
                        "The contractor may not work for anyone else during the term (the US template lets contractors serve other clients).", c,
                        r"exclusively")
            elif re.search(r"solicit[^.]{0,60}(hire or engage|employ or engage)", s, re.I):
                who = side_of(s, ctx.labels)
                months = re.search(r"\((\d+)\) months", s)
                if who == "atliq" and months and int(months.group(1)) >= 24:
                    ctx.fair.append(("Non-solicit", who, s, c["ref"]))
                    ctx.add("nonhire", "Review", "P8", f"{months.group(1)}-month one-way non-hire",
                            f"Only AtliQ is barred from hiring or engaging the other side's people, for {months.group(1)} months after the term.",
                            c, r"solicit", category="Restrictive covenant")
            elif re.search(r"solicit or accept work from any client", s) and ctx.side == "buyer":
                ctx.add("p10-clientban", "Review", "P10", "Client non-solicit on the contractor",
                        "The contractor may not accept work from AtliQ clients for 12 months after the term.", c, r"solicit")


# ------------------------------------------------------------------ P8 NDA mutuality

def check_nda(ctx):
    if "nda" not in ctx.doc["doc_type"].lower() and "non-disclosure" not in ctx.doc["title"].lower():
        return
    titled_mutual = "mutual" in ctx.doc["title"].lower()
    other = "|".join(re.escape(l) for l in ctx.labels["other"]) or "Company"
    mine = "|".join(re.escape(l) for l in ctx.labels["atliq"][1:]) or "Recipient"
    one_way_def = None
    for c in ctx.clauses:
        if re.search(r"\"\*\*Confidential Information\*\*\"\s+means", c["text"]):
            if re.search(r"disclosed (?:or made available )?by or on behalf of (?:the )?(" + other + r") to (?:the )?(" + mine + r")", c["text"]):
                one_way_def = c
    if one_way_def:
        sev = "Serious" if titled_mutual else "Review"
        ctx.add("nda-oneway", sev, "P8", "Titled 'Mutual' but protects only one side" if titled_mutual else "One-way NDA",
                "Only the other side's information is protected and only AtliQ carries obligations. Checklist: 'NDAs -> just sign if mutual' (GlobalMart precedent).",
                one_way_def, r"means")
        ctx.fair.append(("Confidentiality obligations", "atliq", best_quote(one_way_def["text"], r"means"), one_way_def["ref"]))
    for c in ctx.clauses:
        for s in sentences(c["text"]):
            if re.search(r"free to use Residuals", s):
                ctx.add("nda-residuals", "Review", "P8", "One-way residuals clause",
                        "The other side may use whatever its people remember of AtliQ-side information for any purpose; AtliQ gets no equivalent.", c, r"Residuals")
            if re.search(r"continue in perpetuity|survive[^.]*perpetuity", s):
                ctx.add("nda-perpetual", "Review", "P8", "Perpetual obligations",
                        "AtliQ's obligations never end.", c, r"perpetuity")
            if re.search(r"Recipient shall indemnify", s):
                ctx.add("nda-indemnity", "Review", "P8", "One-way indemnity in an NDA",
                        "Only AtliQ indemnifies, for all losses from any breach.", c, r"indemnify")
            if re.search(r"within six \(6\) hours", s):
                ctx.add("nda-6h", "Minor", "P8", "6-hour breach notice", "A 6-hour notification window applies to AtliQ only.", c, r"six \(6\) hours")


# ------------------------------------------------------------------ insurance vs facts (FR-19)

def check_insurance(ctx):
    held = FACTS["cyber_cover_usd"]
    for c in ctx.clauses:
        if not re.search(r"insurance", c["text"] + " " + c["heading"], re.I):
            continue
        for s in sentences(c["text"]):
            amounts = [int(a.replace(",", "")) for a in re.findall(r"\$([\d,]{7,})", s)]
            if not amounts:
                continue
            if re.search(r"cyber", s, re.I):
                req = max(amounts) if re.search(r"cyber[^$]*\$", s, re.I) is None else int(re.search(r"cyber[^$]*\$([\d,]+)", s, re.I).group(1).replace(",", ""))
                if req > held["value"]:
                    ctx.add("insurance-cyber", "Serious", "FR-19 facts", "Insurance required exceeds cover held",
                            f"Requires {money(req)} cyber cover; AtliQ holds {money(held['value'])} (facts table, {held['source']}).",
                            c, r"cyber", exposure={"required": money(req), "held": money(held["value"])}, category="Facts check")
            others = [a for a in amounts if a >= 5_000_000]
            if others and not re.search(r"cyber[^$]*\$", s, re.I) or (others and len(amounts) > 1 and re.search(r"errors and omissions|umbrella", s, re.I)):
                ctx.add("insurance-other", "Review", "FR-19 facts", "Insurance not recorded in the facts table",
                        "E&O / umbrella limits of $5M are required; the facts table has no record of AtliQ's E&O or umbrella cover - confirm with the broker.",
                        c, r"\$5,000,000", category="Facts check")


# ------------------------------------------------------------------ could-not-check (FR-12) and anomalies

def check_unreadable(ctx, bundle_titles):
    text = ctx.doc["text"]
    for c in ctx.clauses:
        m = re.search(r"the (Arabic|German|French|Hindi|Chinese) (text|version) shall prevail", c["text"], re.I)
        if m:
            ctx.could_not_check.append(f"{m.group(1)} text prevails ({c['ref']}) - only the English text was reviewed.")
            ctx.add("lang-prevails", "Review", "FR-12", f"{m.group(1)} version prevails",
                    f"The {m.group(1)} text controls on any inconsistency and was not reviewed. Ask for a certified translation or counsel review.",
                    c, r"shall prevail", category="Could not check")
        if re.search(r"may update[^.]*from time to time[^.]*form part of this Agreement", c["text"]):
            ctx.add("unilateral", "Review", "FR-12", "Terms can change unilaterally",
                    "The other side can update incorporated programme terms by notice; those updates were not and cannot be reviewed now.",
                    c, r"may update", category="Could not check")
        if re.search(r"shared between the Parties in the proportion of", c["text"]) and re.search(r"Partner Services fees", c["text"]):
            ctx.add("revshare", "Review", "FR-13 mutuality", "AtliQ's own services fees pooled into the revenue split",
                    "Joint Deal Revenue, including AtliQ's own implementation fees, is split 80/20 in the partner's favour.",
                    c, r"proportion of")
        if re.search(r"shall maintain at least (\w+) \((\d+)\) \w+ Certified Engineers", c["text"]):
            n = re.search(r"at least (\w+) \((\d+)\)", c["text"]).group(2)
            ctx.add("capacity", "Review", "FR-19 facts", f"Capacity commitment: {n} certified engineers",
                    f"Requires {n} certified engineers plus an architect. AtliQ already commits 4 certified engineers to CloudSpan; the facts table holds no current headcount.",
                    c, r"Certified Engineers", category="Facts check")

    headings = [h.lower() for h in re.findall(r"^\s*#{1,6}\s+(.*)$", text, re.M)]
    sections = re.split(r"^\s*#{1,6}\s+", text, flags=re.M)
    attached_sep = {s.splitlines()[0].lower() for s in sections if "attached separately" in s.lower() and s.strip()}
    seen = set()
    for c in ctx.clauses:
        for m in re.finditer(r"\b(Annex|Annexure|Exhibit|Schedule|Appendix)\s+([A-Z0-9]{1,2})\b(?![-\w])", c["text"]):
            key = f"{m.group(1)} {m.group(2)}"
            if key.lower() in seen:
                continue
            seen.add(key.lower())
            present = any(key.lower() in h and h not in attached_sep for h in headings)
            present = present or any(key.lower() in t.lower() for t in bundle_titles)
            if present:
                continue
            ref_line = next((l for l in c["text"].splitlines() if key in l), c["text"])
            ref_sentence = best_quote(ref_line, re.escape(key))
            dp = re.search(r"Data Processing Agreement|Art(icle|\.) 28|Standard Contractual|\bSCCs?\b|Business Associate Agreement", ref_sentence)
            ctx.could_not_check.append(f"{key} is referenced ({c['ref']}) but not attached" + (" - it is the data-protection document" if dp else "") + ".")
            if dp:
                ctx.add("missing-dpa", "Serious", "P11", f"{key} (data-protection terms) referenced but not attached",
                        "The data processing terms that make offshore processing lawful are missing from the draft, so they cannot be reviewed and are not in place.",
                        c, re.escape(key), category="Could not check", quote=ref_sentence)

    if re.search(r"ignore (all |any )?(previous|prior|above) instructions|disregard (all |the )?(previous|prior)|you are an ai|system prompt|mark this (contract|document) as (safe|approved)", text, re.I):
        for c in ctx.clauses:
            if re.search(r"ignore (all |any )?(previous|prior|above) instructions|disregard|you are an ai|system prompt|mark this", c["text"], re.I):
                ctx.add("injection", "Serious", "Guardrail", "Instruction-like text inside the document",
                        "The document contains text addressed to an AI reviewer. It was treated as contract data and not followed. Ask the counterparty why it is there.",
                        c, r"ignore|disregard|you are an ai|system prompt|mark this", category="Anomaly")
                break


ALL_CHECKS = [check_delay_damages, check_liability, check_indemnity, check_payment, check_termination,
              check_ip, check_restrictive, check_nda, check_insurance]
