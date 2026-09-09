"""
Long-context baseline: the whole corpus in one prompt, no retrieval.

The comparison the RAG arms are measured against. Every file goes in the
prompt with its path, each of the 30 frozen questions is asked separately, and
the model is told to answer with file citations. Scoring then uses the same
expected-file sets as retrieval: did the cited files include every expected
one?

This is a fair fight only because the corpus is small. 113,256 tokens fits a
200k window with room for the answer, so nothing is truncated and no selection
step happens before the model reads. At a realistic codebase size this
baseline is simply unavailable, which is the point of measuring it here.

Trace questions are where this should win. "What calls the recommendation
engine?" requires following a reference across three files; an embedding
model scores each file independently and cannot follow anything.

Cost: the corpus is cached, so the first call pays for the write and the
other 29 read from cache. Roughly $1.50 on Sonnet for all 30.

Usage:
    export ANTHROPIC_API_KEY=...        # or put it in .env
    .venv/bin/python longcontext.py
    .venv/bin/python longcontext.py --model claude-opus-5 --limit 5
"""

import argparse
import json
import os
import re
from pathlib import Path

MODEL = "claude-sonnet-5"

SYSTEM = """You are answering questions about a codebase. The complete source \
is provided below, each file preceded by its path.

Answer the question, then cite every file your answer depends on.

End your reply with exactly one line in this form, listing repository-relative \
paths, comma-separated:

CITED: path/one.kt, path/two.swift

Cite only files you actually used. Do not pad the list."""


def build_corpus_block(path: Path) -> str:
    parts = []
    for line in path.open():
        r = json.loads(line)
        body = r["text"].split("\n\n", 1)[1] if "\n\n" in r["text"] else r["text"]
        parts.append(f"===== FILE: {r['path']} =====\n{body}")
    return "\n\n".join(parts)


def parse_cited(text: str) -> list[str]:
    m = re.findall(r"^CITED:\s*(.+)$", text, re.MULTILINE)
    if not m:
        return []
    return [p.strip() for p in m[-1].split(",") if p.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=Path("corpus/chunks.jsonl"))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--limit", type=int, default=None, help="first N questions")
    ap.add_argument("--out", type=Path, default=Path("eval/results-longcontext.json"))
    args = ap.parse_args()

    from embed import load_dotenv
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("error: ANTHROPIC_API_KEY is not set (env or .env)")

    import anthropic
    client = anthropic.Anthropic()

    corpus = build_corpus_block(args.corpus)
    spec = json.load(open("eval/expected.json"))["questions"][: args.limit]
    print(f"corpus block: {len(corpus):,} chars, {len(spec)} questions, "
          f"model {args.model}")

    rows = []
    for q in spec:
        resp = client.messages.create(
            model=args.model,
            max_tokens=1024,
            system=[
                {"type": "text", "text": SYSTEM},
                # Cached: the other 29 questions read this rather than re-paying.
                {"type": "text", "text": corpus,
                 "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": q["q"]}],
        )
        answer = "".join(b.text for b in resp.content if b.type == "text")
        cited = parse_cited(answer)
        exp = set(q["expected"])
        section = ("locate" if q["id"] < 11 else "explain" if q["id"] < 21
                   else "trace" if q["id"] < 26 else "cross-platform")
        rows.append({
            "id": q["id"], "section": section, "n_expected": len(exp),
            "cited": cited,
            "missed": sorted(exp - set(cited)),
            "covered": exp <= set(cited),
            "n_cited": len(cited),
            "answer": answer[:1500],
            "usage": {"in": resp.usage.input_tokens,
                      "out": resp.usage.output_tokens,
                      "cache_read": getattr(resp.usage, "cache_read_input_tokens", 0),
                      "cache_write": getattr(resp.usage, "cache_creation_input_tokens", 0)},
        })
        print(f"  Q{q['id']:<3} {'PASS' if rows[-1]['covered'] else 'fail'}  "
              f"cited {len(cited)}  missed {[m.split('/')[-1] for m in rows[-1]['missed']]}")

    n = len(rows)
    print(f"\ncoverage: {sum(r['covered'] for r in rows)}/{n}")
    for s in ("locate", "explain", "trace", "cross-platform"):
        sub = [r for r in rows if r["section"] == s]
        if sub:
            print(f"  {s:<16}{sum(r['covered'] for r in sub)}/{len(sub)}")
    tot_read = sum(r["usage"]["cache_read"] for r in rows)
    tot_write = sum(r["usage"]["cache_write"] for r in rows)
    print(f"\ncache: {tot_write:,} written, {tot_read:,} read")
    args.out.write_text(json.dumps(
        {"model": args.model, "metric": "citation coverage", "rows": rows}, indent=2))
    print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
