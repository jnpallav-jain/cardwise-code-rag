"""
Embed a corpus arm with voyage-code-4 and cache the vectors.

Vectors are cached per arm so re-scoring costs nothing. Chunks are embedded
with input_type="document" and questions with input_type="query": Voyage
embeds the two asymmetrically, and getting it wrong degrades retrieval in a
way that looks exactly like a bad chunking strategy.

The API key is read from VOYAGE_API_KEY, which is loaded from a .env file
next to this script if one exists. An already-exported variable wins.

Usage:
    echo 'VOYAGE_API_KEY=...' > .env      # or: export VOYAGE_API_KEY=...
    python embed.py corpus/chunks.jsonl
    python embed.py corpus/chunks-hybrid.jsonl
"""

import json
import os
import sys
from pathlib import Path

import numpy as np


def load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env reader. The key never belongs in the repo, and .env is
    gitignored -- this just saves exporting it in every shell."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

# python-dotenv if present, but imported under another name: binding it to
# `load_dotenv` shadowed the function above, and its no-arg form inspects the
# caller's stack frame, which fails for scripts fed in on stdin.
try:
    from dotenv import load_dotenv as _dotenv_load
    _dotenv_load(Path(__file__).with_name(".env"))
except ImportError:
    pass  # fall back to the reader above, or to whatever is already exported

MODEL = "voyage-code-4"
BATCH = 64


def embed_texts(texts: list[str], input_type: str) -> np.ndarray:
    import voyageai
    load_dotenv()
    if not os.environ.get("VOYAGE_API_KEY"):
        raise SystemExit("error: VOYAGE_API_KEY is not set")
    client = voyageai.Client()
    out = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i:i + BATCH]
        r = client.embed(batch, model=MODEL, input_type=input_type)
        out.extend(r.embeddings)
        print(f"  embedded {min(i + BATCH, len(texts))}/{len(texts)}", file=sys.stderr)
    return np.array(out, dtype=np.float32)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    corpus = Path(sys.argv[1])
    recs = [json.loads(l) for l in corpus.open()]
    print(f"{corpus.name}: {len(recs)} chunks, "
          f"{sum(r['tokens'] for r in recs):,} tokens", file=sys.stderr)

    vecs = embed_texts([r["text"] for r in recs], "document")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)

    out = corpus.with_suffix(".npz")
    np.savez(out, vectors=vecs,
             ids=np.array([r["id"] for r in recs]),
             paths=np.array([r["path"] for r in recs]),
             tokens=np.array([r["tokens"] for r in recs]))
    print(f"wrote {out}  shape={vecs.shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
