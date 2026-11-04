"""Upload intake (FR-01, FR-05): text extraction from PDF / Word / text and a PHI / bulk-personal-data gate."""

import io
import re
import zipfile


def _docx_text(fragment: str) -> str:
    """Run text of a Word fragment, with bold runs kept as **bold** (party names and labels rely on it)."""
    parts = []
    for run in re.findall(r"<w:r[ >].*?</w:r>", fragment, re.S):
        t = "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", run, re.S))
        if "<w:tab/>" in run:
            t = " " + t
        t = t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
        bold = re.search(r"<w:b(?: w:val=\"(?:1|true)\")?/>", run) and not re.search(r'<w:b w:val="(?:0|false)"/>', run)
        parts.append((t, bool(bold and t.strip())))
    merged, cur_bold, buf = [], None, ""
    for t, b in parts:          # merge neighbouring runs with the same weight
        if b != cur_bold and buf:
            merged.append(f"**{buf}**" if cur_bold else buf)
            buf = ""
        cur_bold, buf = b, buf + t
    if buf:
        merged.append(f"**{buf}**" if cur_bold else buf)
    return "".join(merged)


def extract_text(filename: str, data: bytes):
    """Return (text, notes). Scanned PDFs with no text layer are flagged, never guessed (OCR is not bundled)."""
    name = filename.lower()
    notes = []
    if name.endswith((".md", ".txt")):
        return data.decode("utf-8", errors="replace"), notes
    if name.endswith(".docx"):
        xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8", errors="replace")
        body = re.search(r"<w:body>(.*)</w:body>", xml, re.S)
        blocks = re.findall(r"<w:tbl>.*?</w:tbl>|<w:p[ >].*?</w:p>|<w:p/>", body.group(1) if body else xml, re.S)
        out = []
        for b in blocks:
            if b.startswith("<w:tbl>"):
                # tables keep their shape (rate cards, property schedules are read from them)
                for tr in re.findall(r"<w:tr[ >].*?</w:tr>", b, re.S):
                    cells = [_docx_text(c).replace("|", "/").strip() for c in re.findall(r"<w:tc>.*?</w:tc>", tr, re.S)]
                    out.append("| " + " | ".join(cells) + " |")
                out.append("")
                continue
            t = _docx_text(b)
            if not t.strip():
                continue
            plain = t.replace("**", "").strip()
            if re.search(r'<w:pStyle w:val="(Heading|Title)', b) or re.match(r"^(ARTICLE|SCHEDULE|EXHIBIT|ANNEX)\b|^\d+\.\s+[A-Z][A-Z ]+$", plain):
                t = "## " + plain
            out.append(t)
            out.append("")
        return "\n".join(out), notes
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for i, page in enumerate(reader.pages, 1):
            t = page.extract_text() or ""
            if len(t.strip()) < 40:
                notes.append(f"Page {i}: no readable text layer (scan?) - not reviewed; OCR needed")
                t = "[illegible page]"
            pages.append(t)
        return "\n\n".join(pages), notes
    raise ValueError("Unsupported file type - upload PDF, Word (.docx), Markdown or text")


PHI_PATTERNS = {
    "dates of birth": r"\b(DOB|date of birth)\b[^\n]{0,20}\d{1,4}[/-]\d{1,2}[/-]\d{1,4}",
    "SSNs": r"\b\d{3}-\d{2}-\d{4}\b",
    "diagnosis codes (ICD-10)": r"\b[A-TV-Z]\d{2}\.\d{1,2}\b",
    "MRNs": r"\bMRN[:#\s]*\d{5,}",
    "Aadhaar / PAN numbers": r"\b\d{4}\s\d{4}\s\d{4}\b|\b[A-Z]{5}\d{4}[A-Z]\b",
}


def phi_scan(text: str):
    """Contracts describe PHI; they should not contain it. Flag uploads that look like data extracts."""
    hits = {}
    for label, rx in PHI_PATTERNS.items():
        n = len(re.findall(rx, text))
        if n:
            hits[label] = n
    table_rows = len(re.findall(r"^[^\n]*(,|\t)[^\n]*(,|\t)[^\n]*$", text, re.M))
    block = sum(hits.values()) >= 5 or (table_rows > 50 and hits)
    warn = bool(hits) and not block
    return {"block": block, "warn": warn, "hits": hits}
