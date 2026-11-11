"""Load small ward tables and turn them into retrievable text plus exact lookups.

The live ask path does not use this module. `rag.ask` reads outputs/ward_index.csv
and retrieves the PDFs in policy context/ instead.

Vector search is a poor way to answer "which ward is highest". Those questions
are answered by sorting the dataframe. The same rows are also embedded so a
policy question can pull the ward it is about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd
from langchain_core.documents import Document

from rag.config import ROOT, TABLE_FILES

_YEAR = re.compile(r"\b(20\d{2})\b")
_WARD = re.compile(r"\bward\s*0*(\d{1,2})\b", re.I)
_RANK = re.compile(r"\b(highest|lowest|top|bottom|most|least|rank)\b", re.I)
_NUMBER_QUESTION = re.compile(
    r"\b(ward|rank|top|highest|lowest|rate|count|score|risk|pipe|flood|sewer|combined|subsidy|age|diameter)\b",
    re.I,
)


@dataclass
class LoadedTable:
    name: str
    frame: pd.DataFrame


def _drop_geometry(frame: pd.DataFrame) -> pd.DataFrame:
    keep = []
    for column in frame.columns:
        label = str(column).lower()
        if "geom" in label:
            continue
        series = frame[column]
        if series.dtype == object:
            sample = series.dropna().astype(str).head(20)
            if len(sample) and sample.str.len().mean() > 200:
                continue
        keep.append(column)
    return frame.loc[:, keep].copy()


def _read_one(path) -> list[LoadedTable]:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        book = pd.ExcelFile(path)
        tables = []
        for sheet in book.sheet_names:
            frame = _drop_geometry(book.parse(sheet))
            if frame.empty:
                continue
            tables.append(LoadedTable(f"{path.name} :: {sheet}", frame))
        return tables
    frame = _drop_geometry(pd.read_csv(path))
    if frame.empty:
        return []
    return [LoadedTable(path.name, frame)]


def load_tables() -> list[LoadedTable]:
    tables: list[LoadedTable] = []
    for relative in TABLE_FILES:
        path = ROOT / relative
        if not path.exists() or path.stat().st_size > 5_000_000:
            continue
        tables.extend(_read_one(path))
    return tables


def _cell(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value).strip()


def _ward_columns(frame: pd.DataFrame) -> list[str]:
    found = []
    for column in frame.columns:
        label = str(column).lower().replace(" ", "_")
        if label in {"ward", "ward_id", "ward_number", "area_short_code"} or label.startswith("ward"):
            found.append(column)
    return found


def _year_column(frame: pd.DataFrame):
    for column in frame.columns:
        if str(column).lower() == "year":
            return column
    return None


def tables_to_documents(tables: list[LoadedTable]) -> list[Document]:
    documents = []
    for table in tables:
        if len(table.frame) > 400:
            documents.append(
                Document(
                    page_content=(
                        f"Table {table.name} has {len(table.frame)} rows and columns "
                        f"{', '.join(map(str, table.frame.columns))}. "
                        "Use the exact table lookup rather than this summary."
                    ),
                    metadata={"source": table.name, "source_type": "table"},
                )
            )
            continue
        ward_cols = _ward_columns(table.frame)
        year_col = _year_column(table.frame)
        for index, row in table.frame.iterrows():
            lines = [f"Table: {table.name}"]
            for column in table.frame.columns:
                text = _cell(row[column])
                if text:
                    lines.append(f"{column}: {text}")
            metadata = {"source": table.name, "source_type": "table", "row": str(index)}
            if ward_cols:
                metadata["ward_id"] = _cell(row[ward_cols[0]]).lstrip("0") or _cell(row[ward_cols[0]])
            if year_col is not None:
                metadata["year"] = _cell(row[year_col])
            documents.append(Document(page_content="\n".join(lines), metadata=metadata))
    return documents


def _question_tokens(question: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", question.lower()) if len(token) > 3}


def _best_numeric_column(frame: pd.DataFrame, question: str):
    tokens = _question_tokens(question)
    best = None
    best_score = 0
    for column in frame.columns:
        if not pd.api.types.is_numeric_dtype(frame[column]):
            continue
        name_tokens = set(re.findall(r"[a-z0-9]+", str(column).lower()))
        score = len(tokens & name_tokens)
        if score > best_score:
            best = column
            best_score = score
    return best


def _table_is_relevant(table: LoadedTable, question: str) -> bool:
    tokens = _question_tokens(question)
    haystack = set(re.findall(r"[a-z0-9]+", table.name.lower()))
    for column in table.frame.columns:
        haystack.update(re.findall(r"[a-z0-9]+", str(column).lower()))
    if tokens & haystack:
        return True
    return bool(_WARD.search(question) or _YEAR.search(question))


def _filter_frame(frame: pd.DataFrame, question: str) -> pd.DataFrame:
    view = frame
    wards = {str(int(match)) for match in _WARD.findall(question)}
    years = set(_YEAR.findall(question))
    ward_cols = _ward_columns(view)
    if wards and ward_cols:
        key = view[ward_cols[0]].astype(str).str.replace(r"\.0$", "", regex=True).str.lstrip("0")
        view = view.loc[key.isin(wards)]
    year_col = _year_column(view)
    if years and year_col is not None:
        view = view.loc[view[year_col].astype(str).str.slice(0, 4).isin(years)]
    return view


def _render(name: str, frame: pd.DataFrame, limit: int = 25) -> str:
    shown = frame.head(limit)
    header = " | ".join(map(str, shown.columns))
    rows = [" | ".join(_cell(value) for value in row) for row in shown.itertuples(index=False, name=None)]
    note = ""
    if len(frame) > limit:
        note = f"\n(showing {limit} of {len(frame)} rows)"
    return f"Source: {name}\n{header}\n" + "\n".join(rows) + note


def exact_table_context(tables: list[LoadedTable], question: str) -> str:
    """Return real rows for numeric questions. Policy-only questions get no table dump."""
    if not _NUMBER_QUESTION.search(question):
        return "No table filter applied. Use the policy excerpts for this question."

    blocks = []
    for table in tables:
        if not _table_is_relevant(table, question):
            continue
        view = _filter_frame(table.frame, question)
        if view.empty:
            continue
        column = _best_numeric_column(view, question)
        if column is None and _RANK.search(question):
            numeric = view.select_dtypes("number")
            if numeric.shape[1] >= 1:
                view = view.copy()
                view["row_total"] = numeric.sum(axis=1)
                column = "row_total"
        if column is not None and _RANK.search(question):
            ascending = bool(re.search(r"\b(lowest|bottom|least)\b", question, re.I))
            view = view.sort_values(column, ascending=ascending)
        blocks.append(_render(table.name, view))
    if not blocks:
        return "No table rows matched this question."
    return "\n\n".join(blocks)
