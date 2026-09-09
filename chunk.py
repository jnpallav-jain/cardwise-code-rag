"""
Stage 2: split the oversized files in the corpus.

Reads the whole-file corpus from ingest.py and re-chunks it. Two modes, so
the three-way comparison comes out of one code path:

    hybrid   split only files over --threshold; everything else passes
             through untouched. 25 of 119 files today.
    uniform  split every file, ignoring the threshold. The "just chunk
             everything" strategy, as a control.

The whole-file arm is ingest.py's output, used as-is.

Splitting is structural where a parser can be trusted and mechanical where it
can't. tree-sitter's SQL grammar cannot parse `ON CONFLICT ... DO UPDATE SET`,
which appears in every migration here, so SQL gets a hand-written scanner
instead. Any file whose parse yields ERROR nodes falls back to fixed-size.

Nothing is ever dropped: every file's fragments are asserted to reconcatenate
into the original text, byte for byte, before anything is written.

Usage:
    python chunk.py --mode hybrid
    python chunk.py --mode uniform --out corpus/chunks-uniform.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

import tiktoken

TOKENIZER = "o200k_base"
_ENC = tiktoken.get_encoding(TOKENIZER)

# Files at or under this stay whole in hybrid mode.
SPLIT_THRESHOLD = 1500
# A fragment may grow to this before we start a new one.
TARGET_TOKENS = 1200
# Fragments smaller than this get merged into their neighbour, so a one-line
# import block doesn't become its own embedding.
MIN_TOKENS = 200

# ext -> tree-sitter language. SQL is deliberately absent: see module docstring.
TS_LANGUAGES = {
    "kt": "kotlin", "kts": "kotlin", "swift": "swift",
    "js": "javascript", "ts": "typescript", "html": "html", "toml": "toml",
}


def ntokens(s: str) -> int:
    return len(_ENC.encode(s))


# --- splitters: each returns a list of substrings that concatenate to `text` ---

def split_fixed(text: str, target: int = TARGET_TOKENS) -> list[str]:
    """Line-aligned fixed-size. The fallback that always works."""
    out, buf, buf_tok = [], [], 0
    for line in text.splitlines(keepends=True):
        lt = ntokens(line)
        if buf and buf_tok + lt > target:
            out.append("".join(buf))
            buf, buf_tok = [], 0
        buf.append(line)
        buf_tok += lt
    if buf:
        out.append("".join(buf))
    return out or [text]


def split_sql(text: str) -> list[str]:
    """
    Statement boundaries: top-level semicolons only. Skips over single- and
    double-quoted strings, dollar-quoted bodies ($$ ... $$ or $tag$ ... $tag$),
    line comments and block comments -- a semicolon inside any of those is not
    a boundary.
    """
    out, start, i, n = [], 0, 0, len(text)
    while i < n:
        c = text[i]
        if c == "'" or c == '"':
            quote, i = c, i + 1
            while i < n:
                if text[i] == quote:
                    if i + 1 < n and text[i + 1] == quote:  # '' escape
                        i += 2
                        continue
                    break
                i += 1
        elif c == "$":
            end = text.find("$", i + 1)
            tag = text[i:end + 1] if end != -1 else ""
            # A dollar-quote tag is $$ or $ident$; anything else is an operator.
            if tag and (tag == "$$" or tag[1:-1].isidentifier()):
                close = text.find(tag, end + 1)
                i = (close + len(tag) - 1) if close != -1 else n
            # else: fall through, plain $
        elif c == "-" and text.startswith("--", i):
            nl = text.find("\n", i)
            i = n if nl == -1 else nl
        elif c == "/" and text.startswith("/*", i):
            close = text.find("*/", i + 2)
            i = n if close == -1 else close + 1
        elif c == ";":
            out.append(text[start:i + 1])
            start = i + 1
        i += 1
    if start < n:
        out.append(text[start:])
    return [s for s in out if s] or [text]


def split_treesitter(text: str, lang: str) -> list[str] | None:
    """
    One fragment per top-level declaration. Returns None if the grammar is
    unavailable or the parse contains ERROR nodes -- the caller then falls
    back to fixed-size rather than trusting a broken tree.
    """
    try:
        from tree_sitter_language_pack import get_parser
        parser = get_parser(lang)
    except Exception:
        return None
    raw = text.encode("utf-8")
    tree = parser.parse(raw)
    if tree.root_node.has_error:
        return None
    cuts = _cut_points(tree.root_node, raw, TARGET_TOKENS)
    if len(cuts) < 3:
        return None
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b > a:
            out.append(raw[a:b].decode("utf-8"))
    return out or None


def _cut_points(node, raw: bytes, target: int) -> list[int]:
    """
    Byte offsets to cut at, descending into any child too big to embed well.

    A Swift test file is often one top-level class; cutting only at top level
    would give one 4,000-token fragment and the fixed-size fallback would then
    slice it mid-function. Recursing means we cut between test methods instead,
    which is the whole point of using a parser.
    """
    kids = [k for k in node.children if k.end_byte > k.start_byte]
    if not kids:
        return [node.start_byte, node.end_byte]
    cuts = [node.start_byte]
    for k in kids:
        if len(_ENC.encode(raw[k.start_byte:k.end_byte].decode("utf-8", "replace"))) > target:
            inner = _cut_points(k, raw, target)
            cuts.extend(c for c in inner if c > cuts[-1])
        elif k.start_byte > cuts[-1]:
            cuts.append(k.start_byte)
    if node.end_byte > cuts[-1]:
        cuts.append(node.end_byte)
    return cuts


def split_markdown(text: str) -> list[str]:
    out, buf = [], []
    for line in text.splitlines(keepends=True):
        if line.startswith("#") and buf:
            out.append("".join(buf))
            buf = []
        buf.append(line)
    if buf:
        out.append("".join(buf))
    return out or [text]


def fragments_for(text: str, ext: str) -> tuple[list[str], str]:
    """Returns (fragments, strategy-name-for-the-record)."""
    if ext == "sql":
        return split_sql(text), "sql-statement"
    if ext in ("md", "markdown"):
        return split_markdown(text), "md-heading"
    if ext in TS_LANGUAGES:
        frags = split_treesitter(text, TS_LANGUAGES[ext])
        if frags is not None:
            return frags, f"treesitter-{TS_LANGUAGES[ext]}"
        return split_fixed(text), "fixed-fallback"
    return split_fixed(text), "fixed"


def coalesce(frags: list[str]) -> list[str]:
    """
    Merge neighbours so fragments land in [MIN_TOKENS, TARGET_TOKENS].
    A single fragment over TARGET is left alone here and cut by split_fixed
    afterwards -- one 900-line function is still one function.
    """
    merged, buf, buf_tok = [], "", 0
    for f in frags:
        ft = ntokens(f)
        if buf and buf_tok + ft > TARGET_TOKENS:
            merged.append(buf)
            buf, buf_tok = "", 0
        buf += f
        buf_tok += ft
    if buf:
        merged.append(buf)

    out = []
    for f in merged:
        if ntokens(f) > TARGET_TOKENS * 1.5:
            out.extend(split_fixed(f))
        elif out and ntokens(f) < MIN_TOKENS and ntokens(out[-1]) + ntokens(f) <= TARGET_TOKENS * 1.5:
            out[-1] += f          # absorb a runt rather than embed it alone
        else:
            out.append(f)
    # A runt at position 0 has no previous neighbour, so it is pushed forward
    # instead -- otherwise `import XCTest` becomes its own embedding.
    while len(out) > 1 and ntokens(out[0]) < MIN_TOKENS:
        out[1] = out[0] + out[1]
        out.pop(0)
    return out


def main() -> int:
    global TARGET_TOKENS, MIN_TOKENS
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("hybrid", "uniform"), default="hybrid")
    ap.add_argument("--corpus", type=Path, default=Path("corpus/chunks.jsonl"))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--threshold", type=int, default=SPLIT_THRESHOLD)
    ap.add_argument("--target", type=int, default=TARGET_TOKENS,
                    help="max tokens per fragment; drives coalescing")
    args = ap.parse_args()

    # Module-level defaults are the knobs; the flag overrides them so the
    # uniform arm can run at a genuinely small size.
    TARGET_TOKENS = args.target
    MIN_TOKENS = max(50, args.target // 6)
    out_path = args.out or Path(f"corpus/chunks-{args.mode}.jsonl")

    if not args.corpus.exists():
        print(f"error: {args.corpus} not found; run ingest.py first", file=sys.stderr)
        return 1

    records = [json.loads(l) for l in args.corpus.open()]
    out_records, split_files, strategies, failures = [], 0, {}, []

    for r in records:
        header = f"# File: {r['path']}\n# Platform: {r['platform']}\n\n"
        assert r["text"].startswith(header), f"unexpected header in {r['path']}"
        body = r["text"][len(header):]

        if args.mode == "hybrid" and r["tokens"] <= args.threshold:
            parts, strategy = [body], "whole-file"
        else:
            parts, strategy = fragments_for(body, r["ext"])
            parts = coalesce(parts)
            if len(parts) > 1:
                split_files += 1

        # The invariant. A parse failure that silently loses a file is the
        # bug this whole exercise is meant to avoid.
        if "".join(parts) != body:
            failures.append(r["path"])
            parts, strategy = [body], "whole-file (reconstruction failed)"

        strategies[strategy] = strategies.get(strategy, 0) + 1
        for i, part in enumerate(parts, 1):
            part_header = (
                f"# File: {r['path']}\n# Platform: {r['platform']}\n"
                + (f"# Part: {i}/{len(parts)}\n\n" if len(parts) > 1 else "\n")
            )
            out_records.append({
                "id": f"{r['path']}#{i}" if len(parts) > 1 else r["path"],
                "path": r["path"], "platform": r["platform"], "layer": r["layer"],
                "ext": r["ext"], "part": i, "part_count": len(parts),
                "strategy": strategy,
                "tokens": ntokens(part_header + part), "tokenizer": TOKENIZER,
                "text": part_header + part,
            })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in out_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    toks = [r["tokens"] for r in out_records]
    print(f"mode:            {args.mode}")
    print(f"source files:    {len(records)}")
    print(f"files split:     {split_files}")
    print(f"chunks out:      {len(out_records)}")
    print(f"tokens:          {sum(toks):,}")
    print(f"mean / median:   {sum(toks)//len(toks):,} / {sorted(toks)[len(toks)//2]:,}")
    print(f"largest chunk:   {max(toks):,}")
    print(f"written to:      {out_path}\n")
    print("strategy (files):")
    for name, count in sorted(strategies.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<28} {count:>4}")
    if failures:
        print("\n!! reconstruction failed, kept whole:")
        for f in failures:
            print(f"   {f}")
    else:
        print("\nall files reconcatenate to the original, byte for byte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
