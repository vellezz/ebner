"""Vectorize: the vector half of retrieval.

The index stores `fragment id -> vector` and nothing else. Every filtering rule
that matters — thread status, reference_policy, cooldown, fact validity — lives
in D1, because none of them can be expressed as vector similarity and all of
them can be expressed as SQL.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from .config import load
from .d1 import _run


def _index_name() -> str:
    return load("cloudflare.yaml")["vectorize_index"]


def upsert(records: list[tuple[str, list[float]]]) -> int:
    """Write `id -> vector` pairs into the index.

    Vectors are not queryable the instant this returns — an upsert followed
    immediately by a query came back empty, and the same query a minute later
    found everything. It costs nothing in the real pipeline, where indexing
    happens when an entry merges and retrieval happens the next day, but it
    will mislead anyone testing both in one breath.
    """
    if not records:
        return 0

    with NamedTemporaryFile(
        "w", suffix=".ndjson", delete=False, encoding="utf-8", newline="\n"
    ) as handle:
        for fragment_id, vector in records:
            handle.write(json.dumps({"id": fragment_id, "values": vector}) + "\n")
        path = Path(handle.name)

    try:
        _run(["vectorize", "upsert", _index_name(), "--file", str(path)])
    finally:
        path.unlink(missing_ok=True)
    return len(records)


def query(vector: list[float], top_k: int) -> list[dict]:
    """Nearest neighbours, as `{id, score}`.

    The vector goes on the command line, which is what wrangler offers. Values
    are rounded to six decimals first: full float repr for 1024 dimensions
    approaches the Windows command-line limit, and the extra digits change
    cosine similarity by nothing that matters.
    """
    args = ["vectorize", "query", _index_name(), "--top-k", str(top_k), "--vector"]
    args.extend(f"{value:.6f}" for value in vector)

    output = _run(args)
    start = output.find("{")
    if start == -1:
        raise RuntimeError(f"no JSON in vectorize output:\n{output}")
    payload = json.loads(output[start:])
    return payload.get("matches", [])
