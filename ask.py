"""
Ask the codebase a question.

The eval harness only ever runs the frozen thirty. This is the same pipeline
pointed at whatever you type: embed the question, retrieve inside a token
budget, hand the chunks to the model, print the answer and the files it used.

    .venv/bin/python ask.py "How does the recommendation engine rank cards?"
    .venv/bin/python ask.py --show-chunks "What writes to the cards table?"

Needs VOYAGE_API_KEY and ANTHROPIC_API_KEY (env or .env).
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

from embed import MODEL as EMBED_MODEL
from embed import load_dotenv
from generate import retrieve
from longcontext import SYSTEM, parse_cited

ANSWER_MODEL = "claude-sonnet-5"
CORPUS = Path("corpus/chunks-uniform-noheader.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+")
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    ap.add_argument("--budget", type=int, default=4800)
    ap.add_argument("--model", default=ANSWER_MODEL)
    ap.add_argument("--show-chunks", action="store_true",
                    help="list what was retrieved, with scores")
    args = ap.parse_args()
    question = " ".join(args.question)

    load_dotenv()
    for key in ("VOYAGE_API_KEY", "ANTHROPIC_API_KEY"):
        if not os.environ.get(key):
            raise SystemExit(f"error: {key} is not set (env or .env)")

    npz = args.corpus.with_suffix(".npz")
    if not npz.exists():
        raise SystemExit(f"error: {npz} not found — run embed.py on {args.corpus}")
    chunks = [json.loads(l) for l in args.corpus.open()]

    import voyageai
    qv = voyageai.Client().embed(
        [question], model=EMBED_MODEL, input_type="query").embeddings[0]
    qv = np.asarray(qv, dtype=np.float32)
    qv /= np.linalg.norm(qv)

    picked, used, d = retrieve(qv, npz, args.budget)
    if args.show_chunks:
        sims = d["vectors"] @ qv
        print(f"retrieved {len(picked)} chunks, {used:,} tokens:", file=sys.stderr)
        for rank, j in enumerate(picked, 1):
            print(f"  {rank:>2}. {sims[j]:.3f}  {d['paths'][j]}", file=sys.stderr)
        print(file=sys.stderr)

    context = "\n\n".join(
        f"===== FILE: {d['paths'][j]} =====\n{chunks[j]['text']}" for j in picked)
    import anthropic
    resp = anthropic.Anthropic().messages.create(
        model=args.model, max_tokens=4096,
        system=[{"type": "text", "text": SYSTEM},
                {"type": "text", "text": context}],
        messages=[{"role": "user", "content": question}])
    answer = "".join(b.text for b in resp.content if b.type == "text")

    if resp.stop_reason == "max_tokens":
        print("warning: answer hit max_tokens and may be cut off", file=sys.stderr)
    print(answer)
    cited = parse_cited(answer)
    print(f"\n[{len(picked)} chunks, {used:,} tokens retrieved · "
          f"{len(cited)} file{'' if len(cited) == 1 else 's'} cited]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
