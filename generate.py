"""
End-to-end RAG: retrieve, then answer with citations.

Until now the two halves of this project were scored on different metrics.
Retrieval was scored on recall -- were the expected files in the top-k? The
long-context baseline was scored on citation coverage -- did the answer cite
them? Those are not comparable: recall measures whether a file was *available*,
citation coverage measures whether it was *used*.

This closes that. Same retrieval as the eval arms, then the retrieved chunks
go to the model under the same prompt and the same CITED: contract as
longcontext.py. The result is directly comparable to the baseline, and the gap
between recall and citation coverage is the generator's contribution --
positive if it ignores an irrelevant chunk, negative if it fails to use a
relevant one it was handed.

Usage:
    .venv/bin/python generate.py                       # best config
    .venv/bin/python generate.py --corpus corpus/chunks.jsonl --budget 4800
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np

from longcontext import SYSTEM, parse_cited

MODEL = "claude-sonnet-5"


def retrieve(qvec, npz, budget: int):
    d = np.load(npz, allow_pickle=True)
    order = np.argsort(-(d["vectors"] @ qvec))
    picked, used = [], 0
    for j in order:
        if used + d["tokens"][j] > budget and picked:
            break
        picked.append(int(j))
        used += int(d["tokens"][j])
    return picked, used, d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path,
                    default=Path("corpus/chunks-uniform-noheader.jsonl"))
    ap.add_argument("--budget", type=int, default=4800)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=Path("eval/results-rag-e2e.json"))
    args = ap.parse_args()

    from embed import load_dotenv
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("error: ANTHROPIC_API_KEY is not set")
    import anthropic
    client = anthropic.Anthropic()

    npz = args.corpus.with_suffix(".npz")
    chunks = [json.loads(l) for l in args.corpus.open()]
    qvecs = np.load("eval/questions.npz")["vectors"]
    spec = json.load(open("eval/expected.json"))["questions"][: args.limit]
    print(f"{args.corpus.name}, budget {args.budget}, model {args.model}")

    rows = []
    for qi, q in enumerate(spec):
        picked, used, d = retrieve(qvecs[q["id"] - 1], npz, args.budget)
        # The retrieved set the generator was handed. Paths are re-attached
        # here even when the index has no header, so the model can cite.
        context = "\n\n".join(
            f"===== FILE: {d['paths'][j]} =====\n{chunks[j]['text']}" for j in picked)
        resp = client.messages.create(
            model=args.model, max_tokens=4096,
            system=[{"type": "text", "text": SYSTEM},
                    {"type": "text", "text": context}],
            messages=[{"role": "user", "content": q["q"]}])
        answer = "".join(b.text for b in resp.content if b.type == "text")
        cited = parse_cited(answer)
        exp = set(q["expected"])
        available = {str(d["paths"][j]) for j in picked}
        section = ("locate" if q["id"] < 11 else "explain" if q["id"] < 21
                   else "trace" if q["id"] < 26 else "cross-platform")
        rows.append({
            "id": q["id"], "section": section,
            "retrieval_recall": exp <= available,      # was it available?
            "covered": exp <= set(cited),              # was it used?
            "cited": cited, "n_chunks": len(picked), "used_tokens": used,
            "missed": sorted(exp - set(cited)),
            "truncated": resp.stop_reason == "max_tokens",
        })
        r = rows[-1]
        flag = "" if r["retrieval_recall"] == r["covered"] else \
            ("  <- had it, didn't cite" if r["retrieval_recall"] else "  <- cited beyond retrieval")
        print(f"  Q{q['id']:<3} recall={'Y' if r['retrieval_recall'] else 'n'} "
              f"cited={'Y' if r['covered'] else 'n'} "
              f"({len(picked)} chunks, {used} tok){flag}")

    n = len(rows)
    print(f"\nretrieval recall: {sum(r['retrieval_recall'] for r in rows)}/{n}")
    print(f"citation coverage: {sum(r['covered'] for r in rows)}/{n}")
    for s in ("locate", "explain", "trace", "cross-platform"):
        sub = [r for r in rows if r["section"] == s]
        if sub:
            print(f"  {s:<16}{sum(r['retrieval_recall'] for r in sub)}/{len(sub)}"
                  f" -> {sum(r['covered'] for r in sub)}/{len(sub)}")
    args.out.write_text(json.dumps(
        {"corpus": str(args.corpus), "budget": args.budget, "model": args.model,
         "rows": rows}, indent=2))
    print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
