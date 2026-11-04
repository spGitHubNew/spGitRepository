"""Document loading, clause segmentation, definitions, parties and quote checks."""

import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "Dataset"

GENERIC_LABELS = {"party", "parties", "agreement", "effective date", "baa", "master services agreement",
                  "proposed transaction", "purpose", "services", "deliverables", "sow", "initial sow"}

COMPANY_HINT = re.compile(r"\b(Inc|Ltd|LLC|LLP|GmbH|Limited|LIMITED|Corporation|FZ-LLC|Pvt|PRIVATE|INC|Pte)\b|\bCo\.")
WORD_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "eighteen": 18, "twenty": 20, "thirty": 30,
             "forty": 40, "forty-five": 45, "sixty": 60, "ninety": 90}


def norm(s: str) -> str:
    """Normalisation used for quote verification: unicode, markdown emphasis, whitespace, quotes."""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("**", "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_quote(quote: str, source_text: str) -> bool:
    """GR-02: a quote is shown as fact only if it appears verbatim (after normalisation) in the source."""
    if not quote or len(quote.strip()) < 8:
        return False
    return norm(quote) in norm(source_text)


def read_dataset_file(rel: str) -> str:
    return (DATASET / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------- segmentation

CLAUSE_RE = re.compile(r"^\s*(?:\*\*)?(§\s*)?([A-Z]?\d+(?:\.\d+)+|S\d+\.\d+)\.?(?:\*\*)?\s+(.*)$")
PARA_RE = re.compile(r"^\s*(\d{1,2})\.\s+(?!\*\*[A-Z ]+\*\*\s*$)(.+)$")
HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.*)$")
TITLE_RE = re.compile(r"^\*\*([^*]{2,80}?)\.?\*\*\.?\s*")


def segment(text: str):
    """Split a contract into clauses.

    Numbered clauses (11.2, S1.2, 6.1) are clauses. Lettered sub-items are kept with
    their parent. Un-numbered content under a heading (rate cards, schedules,
    property lists, preamble) becomes its own clause so that nothing is skipped.
    """
    lines = text.splitlines()
    clauses = []
    heading = "Preamble"
    cur = None

    def flush():
        nonlocal cur
        if cur and cur["text"].strip():
            cur["text"] = cur["text"].strip()
            clauses.append(cur)
        cur = None

    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.strip().startswith("*(") and line.strip().endswith(")*") and i < 3:
            continue  # provenance note, not contract text
        h = HEADING_RE.match(line)
        if h:
            flush()
            heading = h.group(1).strip().strip("*")
            continue
        m = CLAUSE_RE.match(line)
        if m and not line.strip().startswith("|"):
            flush()
            num = m.group(2)
            body = m.group(3)
            title = ""
            t = TITLE_RE.match(body)
            if t:
                title = t.group(1).strip()
            cur = {"num": num, "ref": "§" + num, "title": title, "heading": heading, "text": body, "line": i + 1}
            continue
        p = PARA_RE.match(line)
        if p and not line.strip().startswith("|") and (cur is None or cur.get("num", "").count(".") == 0):
            # numbered paragraphs (letters) or "6. RESTRICTIVE COVENANT" headings in scans
            body = p.group(2)
            if body.isupper() and len(body) < 60:
                flush()
                heading = body.title()
                continue
            flush()
            cur = {"num": p.group(1), "ref": "¶" + p.group(1), "title": "", "heading": heading, "text": body, "line": i + 1}
            continue
        if cur is None or (cur.get("heading") != heading):
            flush()
            cur = {"num": "", "ref": heading, "title": heading, "heading": heading, "text": "", "line": i + 1}
        cur["text"] += "\n" + line
    flush()

    # a heading-only clause with nothing but signature blocks is not a clause
    out = []
    for c in clauses:
        if not c["num"] and re.search(r"signature|execution|in witness", c["heading"], re.I):
            continue
        out.append(c)
    for idx, c in enumerate(out):
        c["idx"] = idx
    return out


def sentences(text: str):
    flat = re.sub(r"\s*\n\s*", " ", text)
    flat = re.sub(r"^\*\*[^*]{2,80}\*\*\.?\s*", "", flat)  # clause title is not part of the obligation
    parts = re.split(r"(?<=[.;])(?<!U\.S\.)(?<!Inc\.)(?<!Ltd\.)(?<! No\.)(?<! Co\.)(?<!e\.g\.)(?<!i\.e\.)\s+(?=(?:\(?[a-z]\)|[A-Z\"(]))", flat)
    return [p.strip() for p in parts if p.strip()]


def best_quote(clause_text: str, pattern, max_len: int = 420) -> str:
    """Return the verbatim sentence of the clause that matches pattern (or the first sentence)."""
    sents = sentences(clause_text)
    rx = re.compile(pattern, re.I) if isinstance(pattern, str) else pattern
    for s in sents:
        if rx.search(s):
            return trim(s, max_len, rx)
    return trim(sents[0], max_len, rx) if sents else clause_text[:max_len]


def trim(s: str, max_len: int, rx=None) -> str:
    s = s.replace("**", "")
    if len(s) <= max_len:
        return s
    if rx:
        m = rx.search(s)
        if m:
            start = max(0, m.start() - max_len // 3)
            seg = s[start:start + max_len]
            # cut on word boundaries so the quote stays verbatim
            if start > 0:
                seg = seg[seg.find(" ") + 1:]
            return seg.rsplit(" ", 1)[0]
    return s[:max_len].rsplit(" ", 1)[0]


# ---------------------------------------------------------------- definitions

DEF_RE = re.compile(r"\"\*\*([^*]+)\*\*\"\s+(?:or\s+\"\*\*[^*]+\*\*\"\s+)?(?:means|has the meaning|shall mean)")


def definitions(clauses):
    defs = {}
    for c in clauses:
        for m in DEF_RE.finditer(c["text"]):
            defs[m.group(1).strip()] = c["ref"]
    return defs


def attach_definitions(clauses, defs):
    for c in clauses:
        used = []
        for term, ref in defs.items():
            if ref == c["ref"]:
                continue
            if re.search(r"\b" + re.escape(term) + r"\b", c["text"]):
                used.append({"term": term, "ref": ref})
        c["definitions"] = used


# ---------------------------------------------------------------- parties

LABEL_RE = re.compile(r"\"\*\*([^*\"]+)\*\*\"")
NAME_RE = re.compile(r"\*\*([^*]{3,90})\*\*")


def parties(text: str):
    """Return {'atliq': [labels], 'other': [labels], 'atliq_entity': 'Inc'|'Pvt Ltd'|None, 'other_name': str}."""
    lines = [l for l in text.splitlines() if l.strip()][:40]
    region = "\n".join(l for l in lines if not l.strip().startswith("#"))
    events = []  # (pos, kind, value)
    for m in NAME_RE.finditer(region):
        name = m.group(1).strip()
        if region[max(0, m.start() - 1)] == '"':
            continue  # a quoted label, handled below
        if region[m.end():m.end() + 1] != ",":
            continue  # party names are followed by ", a company ..."; titles are not
        is_atliq = "atliq" in name.lower()
        is_company = bool(COMPANY_HINT.search(name)) or bool(re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+$", name))
        if is_atliq or is_company:
            events.append((m.start(), "name", ("atliq" if is_atliq else "other", name)))
    for m in LABEL_RE.finditer(region):
        lab = m.group(1).strip()
        after = region[m.end():m.end() + 30]
        if lab.lower() in GENERIC_LABELS or re.match(r"\s*(means|has the meaning|shall mean|or \")", after):
            continue
        joined = bool(re.match(r"\s*or\s+(?:the\s+)?\"", region[m.end():m.end() + 12]))
        events.append((m.start(), "label", (lab, joined)))
    events.sort()
    out = {"atliq": ["AtliQ"], "other": [], "atliq_entity": None, "other_name": None}
    owner = None
    take = 0
    for _, kind, val in events:
        if kind == "label":
            if take <= 0:
                continue
            val, joined = val
            take = take - 1 + (1 if joined else 0)
        if kind == "name":
            owner = val[0]
            take = 1
            if owner == "atliq" and out["atliq_entity"] is None:
                if re.search(r"atliq inc", val[1], re.I):
                    out["atliq_entity"] = "Inc"
                elif re.search(r"atliq technologies", val[1], re.I):
                    out["atliq_entity"] = "Pvt Ltd"
            if owner == "other" and out["other_name"] is None:
                out["other_name"] = val[1]
        elif owner and val not in out[owner] and val not in out["atliq" if owner == "other" else "other"]:
            out[owner].append(val)
    if out["atliq_entity"] is None:
        if re.search(r"AtliQ Inc", text[:3000]):
            out["atliq_entity"] = "Inc"
        elif re.search(r"AtliQ Technologies", text[:3000], re.I):
            out["atliq_entity"] = "Pvt Ltd"
    return out


def side_of(sentence: str, labels):
    """Which party is the grammatical subject/obligor of a sentence: earliest label wins."""
    best = (10 ** 9, None)
    for side in ("atliq", "other"):
        for lab in labels[side]:
            m = re.search(r"\b" + re.escape(lab) + r"(?:'s|’s)?\b", sentence, re.I if lab.isupper() else 0)
            if not m:
                m = re.search(r"\b" + re.escape(lab.upper()) + r"(?:'S)?\b", sentence)
            if m and m.start() < best[0]:
                best = (m.start(), side)
    return best[1]


# ---------------------------------------------------------------- numbers

def parse_days(s: str):
    m = re.search(r"\((\d+)\)\s*(?:calendar |business |working )?days", s)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d+)\s*(?:calendar |business |working )?days", s)
    return int(m.group(1)) if m else None


def parse_months(s: str):
    m = re.search(r"\((\d+)\)\s*months", s)
    return int(m.group(1)) if m else None


def money(amount, currency="USD"):
    if amount is None:
        return "-"
    if currency == "INR":
        s = f"{amount:,.0f}"
        # Indian grouping
        n = f"{int(round(amount))}"
        if len(n) > 3:
            head, tail = n[:-3], n[-3:]
            head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
            s = head + "," + tail
        return "₹" + s
    sym = {"USD": "$", "EUR": "€"}.get(currency, currency + " ")
    return f"{sym}{amount:,.0f}"


def doc_title(text: str):
    for l in text.splitlines():
        h = HEADING_RE.match(l)
        if h:
            return h.group(1).strip().strip("*")
    return "Untitled document"


def provenance(text: str):
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first.strip("*() ") if first.startswith("*(") else ""


OCR_SIGNS = re.compile(r"\[illegible\]|\b[A-Z]+0[A-Z]+\b|\(l\d\)|\bl\d%|@ l\d|TERMINATI0N|C0VENANT|OCR", re.I)


def ocr_quality(text: str):
    hits = OCR_SIGNS.findall(text)
    illegible = len(re.findall(r"\[illegible\]", text))
    low = len(hits) >= 2 or "scanned" in text[:300].lower()
    return {"low_confidence": low, "signals": len(hits), "illegible": illegible}
