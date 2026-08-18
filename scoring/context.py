"""
Keyword proximity, negative signals, and doc-type inference.

Pure string operations against full_text -- no NER/spaCy here, see ner.py.
"""

WINDOW_CHARS = 50

KEYWORDS = {
    "AADHAAR": ["aadhaar", "aadhar", "uid", "uidai"],
    "PAN": ["pan", "permanent account number", "income tax"],
    "DL": ["dl no", "driving licence", "driving license", "licence number", "license number"],
    "CREDIT_CARD": ["card number", "credit card", "debit card", "card no"],
    "PHONE": ["phone", "mobile", "contact", "tel"],
    "EMAIL": ["email", "e-mail", "mail id"],
}

NEGATIVE_KEYWORDS = [
    "invoice", "order", "ref", "reference", "receipt",
    "quantity", "amount", "sku", "tracking", "identifier",
]

DOC_TYPE_KEYWORDS = [
    "government of india", "uidai", "income tax department", "ministry of",
]


def find_page(page_ctx: dict, page_num: int) -> dict | None:
    for page in page_ctx.get("pages", []):
        if page.get("page_num") == page_num:
            return page
    return None


def _locate(full_text: str, value: str) -> int:
    """Find where `value` sits in `full_text`. -1 if not found."""
    return full_text.find(value)


def _window(full_text: str, idx: int, value_len: int, radius: int = WINDOW_CHARS) -> str:
    start = max(0, idx - radius)
    end = min(len(full_text), idx + value_len + radius)
    return full_text[start:end].lower()


def keyword_proximity(full_text: str, value: str, pii_type: str) -> tuple[bool, str | None]:
    idx = _locate(full_text, value)
    if idx == -1:
        return False, None
    window = _window(full_text, idx, len(value))
    for kw in KEYWORDS.get(pii_type, []):
        if kw in window:
            return True, kw
    return False, None


def negative_signal(full_text: str, value: str) -> tuple[bool, str | None]:
    idx = _locate(full_text, value)
    if idx == -1:
        return False, None
    window = _window(full_text, idx, len(value))
    for kw in NEGATIVE_KEYWORDS:
        if kw in window:
            return True, kw
    return False, None


def doc_type_boost(full_text: str) -> bool:
    lowered = full_text.lower()
    return any(kw in lowered for kw in DOC_TYPE_KEYWORDS)


def _bbox_overlap(a: list, b: list) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def ocr_confidence(page: dict, bbox: list | None) -> float | None:
    """
    Average ocr_conf of tokens whose bbox overlaps the candidate's bbox.

    None if the candidate has no bbox (pasted text, CSV, or any other
    coordinate-less source -- explicitly legal per the detection
    contract) or if no token on the page carries both a bbox and an
    ocr_conf to compare against (pasted-text tokens carry neither).
    """
    if bbox is None:
        return None
    matches = []
    for t in page.get("tokens", []):
        t_bbox = t.get("bbox")
        t_conf = t.get("ocr_conf")
        if t_bbox is None or t_conf is None:
            continue
        if _bbox_overlap(t_bbox, bbox):
            matches.append(t_conf)
    if not matches:
        return None
    return sum(matches) / len(matches)


def get_signals(candidate: dict, page_ctx: dict) -> dict:
    """Collect all context signals for one candidate. No scoring here."""
    page = find_page(page_ctx, candidate["page_num"])
    full_text = page.get("full_text", "") if page else ""

    kw_match, kw = keyword_proximity(full_text, candidate["value"], candidate["pii_type"])
    neg_match, neg_kw = negative_signal(full_text, candidate["value"])

    # detect.py puts its own ocr_conf on the candidate (min across the
    # joined tokens that produced it) -- more precise than reconstructing
    # it via bbox overlap, so prefer it. NER candidates don't carry this
    # field, so fall back to the bbox-overlap heuristic for those.
    ocr_conf = candidate.get("ocr_conf")
    if ocr_conf is None and page is not None:
        ocr_conf = ocr_confidence(page, candidate["bbox"])

    return {
        "keyword_match": kw_match,
        "keyword": kw,
        "negative_match": neg_match,
        "negative_keyword": neg_kw,
        "doc_type_boost": doc_type_boost(full_text),
        "ocr_conf": ocr_conf,
    }
