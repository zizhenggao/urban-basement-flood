"""Paths and models for the policy-plus-ward-index RAG app."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = ROOT / "rag" / "chroma"
POLICY_DIR = ROOT / "policy context"
WARD_INDEX = ROOT / "outputs" / "ward_index.csv"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"

POLICY_EXTENSIONS = {".pdf", ".md"}

# Raw request dumps and map geometry are not useful chunks.
SKIP_NAME_PARTS = (
    "sr2026",
    "service-requests",
    "geojson",
    ".shp",
)

# Kept for the older table helper. The live ask path reads WARD_INDEX instead.
TABLE_FILES = (
    "ward_sewer_features.csv",
    "Basement Flooding by Ward_before 2018.csv",
    "basement-flooding-by-ward.xlsx",
    "ward_locations.csv",
    "data/ward_year.csv",
)

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
