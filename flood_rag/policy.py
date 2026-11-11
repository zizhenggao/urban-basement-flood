"""Read the three BFPP PDFs locally and search them with the ward index.

Subsidy counts are parsed from each ward page of the profile summary.
Ask-time search uses one TF-IDF index over those pages and over plain-language
passages from the ward index. An optional local Ollama model writes a short
paragraph from the passages search already found. Nothing here calls a paid API.
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


class PolicyIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
        self.matrix = self.vectorizer.fit_transform(c.text for c in chunks)

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        """Top policy pages and top ward-index passages for one question.

        Both sources share one TF-IDF space. Each side keeps its own top k so
        a policy-heavy question still returns ward rows, and the reverse.
        """
        mentioned = {
            int(n)
            for n in re.findall(r"ward\s*(\d{1,2})", query, flags=re.I)
            if 1 <= int(n) <= 25
        }
        q = self.vectorizer.transform([query])
        scores = cosine_similarity(q, self.matrix).ravel().copy()
        if mentioned:
            for i, chunk in enumerate(self.chunks):
                if chunk.ward_id in mentioned:
                    scores[i] += 1.0
        policy = [i for i, chunk in enumerate(self.chunks) if chunk.source != "ward index"]
        wards = [i for i, chunk in enumerate(self.chunks) if chunk.source == "ward index"]
        picked = self._top(policy, scores, k) + self._top(wards, scores, k)
        picked.sort(key=lambda i: scores[i], reverse=True)
        return [(self.chunks[i], float(scores[i])) for i in picked]

    @staticmethod
    def _top(idxs: list[int], scores, k: int) -> list[int]:
        ordered = sorted(idxs, key=lambda i: scores[i], reverse=True)
        return [i for i in ordered if scores[i] > 0][:k]

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
            candidates = [
                i
                for i, chunk in enumerate(self.chunks)
                if chunk.ward_id == ward_id and chunk.source != "ward index"
            ]
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


def ollama_answer(question: str, hits: list[tuple[Chunk, float]], model: str) -> tuple[str | None, str | None]:
    """Generate from the retrieved excerpts. Returns (answer, error)."""
    def _block(hit: Chunk) -> str:
        if hit.source == "ward index":
            label = "ward index ranking" if hit.ward_id is None else f"ward index ward {hit.ward_id}"
        else:
            label = f"{hit.source} p.{hit.page}"
        return f"[{label}]\n{hit.text[:1600]}"

    rankings = [hit for hit, _ in hits if hit.source == "ward index" and hit.ward_id is None]
    ward_rows = [hit for hit, _ in hits if hit.source == "ward index" and hit.ward_id is not None]
    policy = [hit for hit, _ in hits if hit.source != "ward index"]
    blocks = [_block(hit) for hit in rankings + ward_rows + policy]
    prompt = (
        "You advise a Toronto city planner on basement-flood outreach. "
        "Excerpts come from two retrieved sources: the ward index, and Basement Flooding Protection Program pages. "
        "If a ward index ranking excerpt is present, name the wards in that order. "
        "Do not replace that list with other wards. "
        "Use individual ward excerpts only to explain the wards already named in the ranking. "
        "Use policy excerpts for what the program offers, who is eligible, and which study area applies. "
        "Repeat each rank in the direction the excerpt states. "
        "If an excerpt says residents rarely report basement floods, do not call those reports high. "
        "If a number is not in the excerpts, say it is not in the excerpts. "
        "Write in plain language.\n\n"
        f"Excerpts:\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}\nAnswer:"
    )
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:240]
        return None, f"Ollama returned {exc.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None, (
            "Ollama is not running. Start it with `ollama serve`, then "
            f"`ollama pull {model}`."
        )
    text = payload.get("response", "").strip()
    if not text:
        return None, "Ollama returned an empty answer."
    return text, None


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
