"""Read experiment files/directories and split into chunks for the LLM."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

SUPPORTED_EXTENSIONS = {".md", ".txt", ".log", ".json", ".csv"}


@dataclass
class Chunk:
    source: str       # original file path
    index: int        # chunk number within that file (0-based)
    total: int        # total chunks for this file
    text: str         # raw text content


def ingest(paths: List[str], chunk_size: int = 12000) -> List[Chunk]:
    """
    Read all files from the given paths (files or directories) and return
    a flat list of Chunks. Large files are split into overlapping windows.
    """
    file_paths = _collect_files(paths)
    chunks: List[Chunk] = []
    for fp in file_paths:
        text = _read_file(fp)
        if not text.strip():
            continue
        file_chunks = _split(text, chunk_size)
        for i, chunk_text in enumerate(file_chunks):
            chunks.append(Chunk(source=fp, index=i, total=len(file_chunks), text=chunk_text))
    return chunks


def _collect_files(paths: List[str]) -> List[str]:
    collected = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for root, _, files in os.walk(path):
                for f in sorted(files):
                    fp = os.path.join(root, f)
                    if Path(fp).suffix.lower() in SUPPORTED_EXTENSIONS:
                        collected.append(fp)
        elif path.is_file():
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                collected.append(str(path))
            else:
                print(f"[warn] Skipping unsupported file type: {p}")
        else:
            print(f"[warn] Path not found: {p}")
    return collected


def _read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        print(f"[warn] Could not read {path}: {e}")
        return ""


def _split(text: str, chunk_size: int) -> List[str]:
    """Split text into chunks of ~chunk_size chars, breaking on newlines."""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            # Try to break on a newline boundary
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline + 1
        chunks.append(text[start:end])
        start = end
    return chunks
