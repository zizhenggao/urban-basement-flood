"""Build a local Chroma index of the policy-context documents.

Ward numbers are not embedded. `rag.ask` reads `outputs/ward_index.csv`
directly so ranks stay exact. Run from the project root:

    .\\.venv-rag\\Scripts\\python -m rag.build_index
"""

from __future__ import annotations

import shutil

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    INDEX_DIR,
    POLICY_DIR,
    POLICY_EXTENSIONS,
    SKIP_NAME_PARTS,
)
from rag.embeddings import LocalEmbeddings


def _policy_files():
    if not POLICY_DIR.is_dir():
        raise SystemExit(f"No policy folder at {POLICY_DIR}")
    files = [
        path
        for path in sorted(POLICY_DIR.iterdir())
        if path.is_file() and path.suffix.lower() in POLICY_EXTENSIONS
        and not any(part in path.name.lower() for part in SKIP_NAME_PARTS)
    ]
    if not files:
        raise SystemExit(f"No policy documents in {POLICY_DIR}")
    return files


def load_policy_documents():
    documents = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    for path in _policy_files():
        if path.suffix.lower() == ".pdf":
            loaded = PyPDFLoader(str(path)).load()
        else:
            loaded = TextLoader(str(path), encoding="utf-8").load()
        for doc in loaded:
            doc.metadata["source"] = path.name
            doc.metadata["source_type"] = "policy"
            if "page" in doc.metadata:
                doc.metadata["page"] = int(doc.metadata["page"]) + 1
        chunks = [doc for doc in splitter.split_documents(loaded) if doc.page_content.strip()]
        print(f"{path.name}: {len(chunks)} chunks")
        documents.extend(chunks)
    return documents


def build(rebuild: bool = True) -> int:
    documents = load_policy_documents()
    if not documents:
        raise SystemExit(f"No text extracted from {POLICY_DIR}")

    if rebuild and INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    Chroma.from_documents(
        documents=documents,
        embedding=LocalEmbeddings(),
        persist_directory=str(INDEX_DIR),
        collection_name="flood_policy",
    )
    (INDEX_DIR / "indexed_from.txt").write_text(
        "policy context\n",
        encoding="utf-8",
    )
    print(f"indexed {len(documents)} policy chunks from {POLICY_DIR.name} into {INDEX_DIR}")
    return len(documents)


if __name__ == "__main__":
    build(rebuild=True)
