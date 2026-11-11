"""Read the three BFPP PDFs locally.

Subsidy counts are parsed from each ward page of the profile summary.
A TF-IDF index answers follow-up questions from those pages. An optional
local Ollama model can turn the retrieved pages into a short paragraph.
Nothing here calls a paid API.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

import pandas as pd
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from flood_rag.paths import OUTPUT, POLICY_DIR, SUMMARY_PDF_NAME

_WARD_RE = re.compile(r"Ward\s+(\d+)\s*:\s*([^\n]+)")
_MONEY_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*M")


@dataclass
class Chunk:
    source: str
    page: int
    ward_id: int | None
    text: str


def _summary_path():
    path = POLICY_DIR / SUMMARY_PDF_NAME
    if not path.exists():
        matches = list(POLICY_DIR.glob("*Summary*.pdf"))
        if not matches:
            raise FileNotFoundError(f"No BFPP summary PDF in {POLICY_DIR}")
        return matches[0]
    return path


def _page_text(path) -> list[tuple[int, str]]:
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        pages.append((i, page.extract_text() or ""))
    return pages


def _subsidy_fields(text: str) -> tuple[float, float, float]:
    """Return properties with a device, properties without, and city $ millions.

    The ward-profile pages are laid out as maps, so pypdf does not keep the
    subsidy columns in a stable order. A protected home is the count that
    implies about $1,700 of city subsidy. The largest other count is the
    unprotected stock.
    """
    flat = re.sub(r"[ \t]+", " ", text)
    # Subsidy payments on these pages are under $12M. Larger figures are
    # capital-project costs and can divide a home count into a fake $1,700.
    monies = [
        float(m.replace(",", ""))
        for m in _MONEY_RE.findall(flat)
        if float(m.replace(",", "")) <= 12
    ]
    stripped = _MONEY_RE.sub(" ", flat)
    stripped = re.sub(r"\b\d[\d,.]*(?:\s*(?:km|m|%))", " ", stripped, flags=re.I)
    nums = []
    for raw in re.findall(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{3,5}\b", stripped):
        value = int(raw.replace(",", ""))
        if value == 68000 or 1990 <= value <= 2035 or value < 150:
            continue
        nums.append(value)
    if not monies or not nums:
        raise ValueError(f"subsidy block not found: {flat[:240]!r}")
    best: tuple[float, int] | None = None
    for million in monies:
        dollars = million * 1_000_000
        for count in set(nums):
            per_home = dollars / count
            if 1400 <= per_home <= 2300:
                error = abs(per_home - 1700)
                if best is None or error < best[0]:
                    best = (error, count)
    if best is None:
        raise ValueError(f"no count matches a ~$1,700 subsidy in: {flat[:240]!r}")
    with_fpd = best[1]
    matched = [
        million
        for million in monies
        if 1400 <= (million * 1_000_000) / with_fpd <= 2300
    ]
    city_million = min(matched)
    unprotected = [n for n in set(nums) if n > with_fpd]
    if not unprotected:
        raise ValueError(f"no unprotected-home count alongside {with_fpd}")
    return float(with_fpd), float(max(unprotected)), city_million


def load_subsidy_stock() -> pd.DataFrame:
    """Properties with and without a flood-protection device, June 2025."""
    rows = []
    for page, text in _page_text(_summary_path()):
        match = _WARD_RE.search(text)
        if not match:
            continue
        ward_id = int(match.group(1))
        name = re.sub(r"\s+", " ", match.group(2)).strip(" -")
        with_fpd, without, city_million = _subsidy_fields(text)
        rows.append(
            {
                "ward_id": ward_id,
                "pdf_ward_name": name,
                "properties_with_fpd": with_fpd,
                "properties_without_fpd": without,
                "city_subsidy_million": city_million,
                "summary_page": page,
            }
        )
    frame = pd.DataFrame(rows).drop_duplicates("ward_id").sort_values("ward_id")
    if len(frame) != 25:
        raise RuntimeError(f"expected 25 ward pages, parsed {len(frame)}")
    return frame.reset_index(drop=True)


def load_chunks() -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(POLICY_DIR.glob("*.pdf")):
        for page, text in _page_text(path):
            cleaned = re.sub(r"[^\S\n]+", " ", text)
            cleaned = re.sub(r"\n{2,}", "\n", cleaned).strip()
            if len(cleaned) < 80:
                continue
            match = _WARD_RE.search(cleaned)
            ward_id = int(match.group(1)) if match else None
            chunks.append(Chunk(path.name, page, ward_id, cleaned))
    return chunks


def _readable(text: str) -> bool:
    """False for map pages whose extracted text is mostly stray symbols and labels."""
    words = re.findall(r"[A-Za-z][A-Za-z'\-]+", text)
    if len(words) < 12:
        return False
    long_words = [w for w in words if len(w) >= 3]
    return len(long_words) / max(1, len(text.split())) >= 0.55


def _split_sentences(text: str, target: int) -> list[str]:
    flat = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z$(\d])", flat)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > target:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _trim_debris(text: str) -> str:
    """Drop leading map symbols and stray labels so a passage starts at real words."""
    tokens = text.split()
    start = 0
    while start < len(tokens) and not re.search(r"[A-Za-z]{3,}", tokens[start]):
        start += 1
    return " ".join(tokens[start:])


def load_passages(chunks: list[Chunk] | None = None, target: int = 650) -> list[Chunk]:
    """Split each PDF page into passages of about `target` characters.

    A whole page mixes maps, legends and text, so a page-level match is vague and
    the useful sentence gets lost. Passages that are mostly map debris are dropped.
    """
    passages: list[Chunk] = []
    for page in chunks if chunks is not None else load_chunks():
        for piece in _split_sentences(page.text, target):
            piece = _trim_debris(piece)
            if len(piece) >= 120 and _readable(piece):
                passages.append(Chunk(page.source, page.page, page.ward_id, piece))
    return passages


class PolicyIndex:
    def __init__(self, chunks: list[Chunk], sublinear_tf: bool = False):
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), min_df=1, sublinear_tf=sublinear_tf
        )
        self.matrix = self.vectorizer.fit_transform(c.text for c in chunks)

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        mentioned = {
            int(n)
            for n in re.findall(r"ward\s*(\d{1,2})", query, flags=re.I)
            if 1 <= int(n) <= 25
        }
        q = self.vectorizer.transform([query])
        scores = cosine_similarity(q, self.matrix).ravel()
        if mentioned:
            for i, chunk in enumerate(self.chunks):
                if chunk.ward_id in mentioned:
                    scores[i] += 1.0
        order = scores.argsort()[::-1][:k]
        return [(self.chunks[i], float(scores[i])) for i in order if scores[i] > 0]

    def pages_for_wards(self, query: str, ward_ids: list[int], limit: int = 3) -> list[tuple[Chunk, float]]:
        """Best policy page for each priority ward, so study-area text is available."""
        if not ward_ids:
            return []
        q = self.vectorizer.transform([query])
        scores = cosine_similarity(q, self.matrix).ravel()
        found: list[tuple[Chunk, float]] = []
        seen: set[tuple[str, int]] = set()
        for ward_id in ward_ids:
            if len(found) >= limit:
                break
            candidates = [i for i, chunk in enumerate(self.chunks) if chunk.ward_id == ward_id]
            if not candidates:
                continue
            best = max(candidates, key=lambda i: (scores[i], -self.chunks[i].page))
            chunk = self.chunks[best]
            key = (chunk.source, chunk.page)
            if key in seen:
                continue
            seen.add(key)
            found.append((chunk, float(scores[best])))
        return found


def ollama_answer(
    question: str,
    hits: list[tuple[Chunk, float]],
    model: str,
    ward_brief: str,
) -> str | None:
    """Return a short answer from a local Ollama server, or None if it is down."""
    context = "\n\n".join(
        f"[{hit.source} p.{hit.page}]\n{hit.text[:1500]}" for hit, _ in hits
    )
    prompt = (
        "You advise a Toronto city planner on where to do basement-flood outreach. "
        "Use the ward index for which wards to contact and why. "
        "The priority rank is already decided; do not invent or reorder it. "
        "Use the policy excerpts only for what the program offers, who is eligible, "
        "and which study area applies. "
        "If a number is in neither source, say it is not in the sources. "
        "Write in plain language.\n\n"
        f"Ward index:\n{ward_brief}\n\n"
        f"Policy excerpts:\n{context}\n\n"
        f"Question: {question}\nAnswer:"
    )
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None
    return payload.get("response", "").strip() or None


def save_chunks(chunks: list[Chunk]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "policy_chunks.jsonl"
    with path.open("w") as handle:
        for chunk in chunks:
            handle.write(
                json.dumps(
                    {
                        "source": chunk.source,
                        "page": chunk.page,
                        "ward_id": chunk.ward_id,
                        "text": chunk.text,
                    }
                )
                + "\n"
            )
