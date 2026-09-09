"""
Score the three arms against the frozen eval set, two ways.

  recall@5        the frozen metric: top 5 CHUNKS, pass if every expected
                  file appears among them. Whole-file chunking gets ~4,760
                  tokens of context for those 5 slots; uniform-400 gets
                  ~1,800. The metric does not control for that.

  recall@budget   the same question at equal context: take chunks in rank
                  order until --budget tokens are used, then check. This is
                  what makes the three arms comparable.

Both are reported. Neither is presented as the number on its own.

Usage:
    python score.py                      # all arms that have vectors
    python score.py --budget 4800
"""

import argparse
import json
from pathlib import Path

import numpy as np

ARMS = {
    "whole-file": "corpus/chunks.jsonl",
    "hybrid": "corpus/chunks-hybrid.jsonl",
    "uniform-400": "corpus/chunks-uniform.jsonl",
}
SECTIONS = {"locate": range(1, 11), "explain": range(11, 21),
            "trace": range(21, 26), "cross-platform": range(26, 31)}


def section_of(qid: int) -> str:
    return next(n for n, r in SECTIONS.items() if qid in r)


def rank(qvec, vecs):
    return np.argsort(-(vecs @ qvec))


def files_at_k(order, paths, k):
    return {paths[i] for i in order[:k]}


def files_in_budget(order, paths, tokens, budget):
    got, used = set(), 0
    for i in order:
        if used + tokens[i] > budget and got:
            break
        got.add(paths[i])
        used += int(tokens[i])
    return got


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=4800,
                    help="token budget for the equal-context metric")
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    spec = json.load(open("eval/expected.json"))["questions"]
    available = {n: Path(p).with_suffix(".npz")
                 for n, p in ARMS.items() if Path(p).with_suffix(".npz").exists()}
    if not available:
        raise SystemExit("no vectors found; run embed.py on each arm first")

    from embed import embed_texts
    qvecs = embed_texts([q["q"] for q in spec], "query")
    qvecs /= np.linalg.norm(qvecs, axis=1, keepdims=True)

    results = {}
    for arm, npz in available.items():
        d = np.load(npz, allow_pickle=True)
        vecs, paths, tokens = d["vectors"], d["paths"], d["tokens"]
        rows = []
        for qi, q in enumerate(spec):
            order = rank(qvecs[qi], vecs)
            exp = set(q["expected"])
            rows.append({
                "id": q["id"], "section": section_of(q["id"]),
                "n_expected": len(exp),
                "at_k": exp <= files_at_k(order, paths, args.k),
                "at_budget": exp <= files_in_budget(order, paths, tokens, args.budget),
            })
        results[arm] = rows

    print(f"\n{'arm':<13}{'recall@'+str(args.k):>12}{'recall@'+str(args.budget)+'tok':>18}")
    for arm, rows in results.items():
        k = sum(r["at_k"] for r in rows)
        b = sum(r["at_budget"] for r in rows)
        print(f"{arm:<13}{k:>7}/{len(rows)} {k/len(rows)*100:>3.0f}%"
              f"{b:>10}/{len(rows)} {b/len(rows)*100:>3.0f}%")

    print(f"\nby section (recall@{args.k} / recall@budget):")
    print(f"  {'section':<16}" + "".join(f"{a:>18}" for a in results))
    for name, rng in SECTIONS.items():
        line = f"  {name:<16}"
        for arm, rows in results.items():
            sub = [r for r in rows if r["id"] in rng]
            line += f"{sum(r['at_k'] for r in sub):>8}/{len(sub)}"
            line += f" {sum(r['at_budget'] for r in sub):>3}/{len(sub)}".rjust(8)
        print(line)

    Path("eval/results.json").write_text(json.dumps(
        {"budget": args.budget, "k": args.k, "arms": results}, indent=2))
    print("\nper-question detail written to eval/results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
