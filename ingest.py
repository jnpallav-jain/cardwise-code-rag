"""
Ingest the CardWise codebase into a flat JSONL corpus.

Stage 1: whole-file chunking. One record per file, with the path as a header
so a chunk retrieved in isolation still says what it is.

Usage:
    python ingest.py /path/to/CardWise
    python ingest.py /path/to/CardWise --out corpus/chunks.jsonl
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import tiktoken

# Real token counts, not chars // 4. The estimate was ~5% high in aggregate
# but off by -28%..+25% on individual files, which is enough to reorder the
# largest ones -- and this number decides what gets split in stage 2.
#
# o200k_base is OpenAI's; Anthropic's tokenizer differs but is in the same
# range for code. Named here so any number we report can say what produced it.
TOKENIZER = "o200k_base"
_ENC = tiktoken.get_encoding(TOKENIZER)

# Files above this many tokens get split in stage 2. One embedding vector
# cannot represent 4,000 tokens of unrelated code: the specifics average out.
SPLIT_THRESHOLD = 1500

# Paths we never index. Everything else in `git ls-files` is kept on purpose,
# including tests and migrations.
#
# Two kinds of exclusion here. The first is tooling state and generated
# resources -- no question has its answer in a launcher icon or a Gradle
# wrapper, so indexing them only adds chunks that can win a retrieval slot
# without ever being right. The second is editor state that carries a local
# username, which has no business in a corpus that might get shared.
EXCLUDE_PREFIXES = (
    "supabase/.temp/",
    ".idea/",
    "supabase/.branches/",
    "gradle/wrapper/",
    "app/src/main/res/drawable/",
    "app/src/main/res/mipmap",
    "ios/CardWise/Sources/Assets.xcassets/",
    "ios/CardWiseKit/.swiftpm/",
)

EXCLUDE_EXACT = (
    "gradlew",
    "gradlew.bat",
    # ~1,000 tokens of base64 certificate hashes: high-entropy noise that
    # draws spurious embedding matches.
    "app/src/main/res/values/font_certs.xml",
)

EXCLUDE_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".ttf", ".otf", ".woff", ".woff2",
    ".jar",
)

# Path prefix -> platform tag. First match wins, so order matters.
PLATFORM_RULES = [
    ("app/", "android"),
    ("ios/", "ios"),
    ("supabase/", "backend"),
    ("admin/", "admin"),
]

# Heuristics for a rough layer tag. Cheap, and good enough to filter on.
# Matched against the lowercased path, so iOS's /Domain/ and /Data/ land on
# the same tags as Android's /domain/ and /data/. Test rules come first: a
# test that lives under /data/ is a test, not a data-layer file.
#
# The needles are deliberately more than the bare word -- "test" on its own
# would tag anything with "latest" in the path.
LAYER_RULES = [
    ("/test/", "test"),
    ("tests/", "test"),
    ("test.kt", "test"),
    ("test.swift", "test"),
    ("/ui/", "ui"),
    ("/screens/", "ui"),
    ("/components/", "ui"),
    ("view.swift", "ui"),
    ("/domain/", "domain"),
    ("/data/", "data"),
    ("/migrations/", "schema"),
]


def git_files(repo: Path) -> list[str]:
    """Tracked files only. Anything gitignored never reaches us."""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.splitlines()


def keep(path: str) -> bool:
    if path.startswith(EXCLUDE_PREFIXES):
        return False
    if path.endswith(EXCLUDE_SUFFIXES):
        return False
    if path in EXCLUDE_EXACT:
        return False
    return True


def platform_of(path: str) -> str:
    for prefix, tag in PLATFORM_RULES:
        if path.startswith(prefix):
            return tag
    return "root"


def layer_of(path: str) -> str:
    lowered = path.lower()
    for needle, tag in LAYER_RULES:
        if needle in lowered:
            return tag
    return "other"


def build_record(repo: Path, rel: str) -> dict | None:
    full = repo / rel
    try:
        text = full.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None  # binary or unreadable; skipped and reported

    platform = platform_of(rel)
    header = f"# File: {rel}\n# Platform: {platform}\n\n"

    return {
        "id": rel,
        "path": rel,
        "platform": platform,
        "layer": layer_of(rel),
        "ext": Path(rel).suffix.lstrip(".") or "none",
        "lines": text.count("\n") + 1,
        "tokens": len(_ENC.encode(header + text)),
        "tokenizer": TOKENIZER,
        "text": header + text,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path, help="path to the CardWise repo")
    ap.add_argument("--out", type=Path, default=Path("corpus/chunks.jsonl"))
    args = ap.parse_args()

    if not (args.repo / ".git").exists():
        print(f"error: {args.repo} is not a git repo", file=sys.stderr)
        return 1

    all_files = git_files(args.repo)
    kept = [f for f in all_files if keep(f)]

    records, skipped = [], []
    for rel in kept:
        rec = build_record(args.repo, rel)
        (records if rec else skipped).append(rec if rec else rel)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # --- summary: this is the part you actually read ---
    total_tokens = sum(r["tokens"] for r in records)
    print(f"tracked files:   {len(all_files)}")
    print(f"excluded:        {len(all_files) - len(kept)}")
    print(f"unreadable:      {len(skipped)}")
    print(f"indexed:         {len(records)}")
    print(f"tokens ({TOKENIZER}): {total_tokens:,}")
    print(f"written to:      {args.out}")
    # Name them. A binary that silently vanishes is a binary you never
    # notice you're missing.
    for rel in skipped:
        print(f"  skipped (unreadable): {rel}")
    print()

    by_platform: dict[str, list] = {}
    for r in records:
        by_platform.setdefault(r["platform"], []).append(r)
    print("by platform:")
    for name, rs in sorted(by_platform.items(), key=lambda kv: -len(kv[1])):
        toks = sum(r["tokens"] for r in rs)
        print(f"  {name:<9} {len(rs):>4} files  {toks:>8,} tokens")

    # Whole-file chunking only holds if files stay small. Flag the ones
    # that don't -- these are the candidates for splitting in stage 2.
    over = sorted(
        (r for r in records if r["tokens"] > SPLIT_THRESHOLD),
        key=lambda r: -r["tokens"],
    )
    if over:
        share = len(over) / len(records) * 100
        print(
            f"\nfiles over {SPLIT_THRESHOLD:,} tokens: {len(over)} of "
            f"{len(records)} ({share:.0f}% of the corpus) -- these get split"
        )
        for r in over[:10]:
            print(f"  {r['tokens']:>6,}  {r['path']}")
        if len(over) > 10:
            print(f"  ... and {len(over) - 10} more")
    else:
        print(f"\nno file exceeds {SPLIT_THRESHOLD:,} tokens.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
