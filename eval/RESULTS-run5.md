# Run 5 — is `locate` real retrieval, or filename matching?

Every chunk carried a `# File: <path>` header. A question like "Where is the
wallet screen implemented on iOS?" could be answered by matching the words in
the question to the words in the path, without the file's contents mattering
at all. Locate scored 10/10, which is exactly the score a filename-matching
artifact would produce.

Test: strip the header, re-embed, re-score. Nothing else changes.

| corpus                  | locate @5 / @bud | trace @5 / @bud | overall @5 | @4,800 tok |
|-------------------------|------------------|-----------------|------------|------------|
| uniform-400 with header |   10/10 · 10/10  |    0/5 · 1/5    |   16/30    |   19/30    |
| uniform-400 NO header   |    9/10 · 10/10  |    1/5 · 3/5    |   16/30    | **23/30**  |
| whole-file with header  |    9/10 ·  9/10  |    1/5 · 0/5    |   16/30    |   12/30    |
| whole-file NO header    |    9/10 ·  8/10  |    1/5 · 0/5    |   16/30    |   10/30    |

## Answer: it is real retrieval

Removing every filename costs **one** locate question out of ten, and at equal
context it costs nothing (10/10 either way). Locate holds at 9/10 with no path
information anywhere in the index.

The single casualty is Q6, "Where is the Supabase project configured?" —
expected `supabase/config.toml`. Without the filename it returns
`Config.sample.xcconfig`, `supabaseClient.js`, `SupabaseClient.kt`,
`config.js`, `SupabaseClient.swift`: five files that are genuinely about
Supabase configuration. That is a reasonable answer to the question as asked,
and it is the one case where the path really was carrying the answer.

So the locate number can go in a README. It is not an artifact.

## The unplanned finding: the header was costing more than it bought

Header text was **8,913 tokens across 334 chunks** — 7.4% of the uniform-400
corpus, about 27 tokens per chunk, repeated for every fragment of a split
file. Removing it:

- frees roughly two extra chunks inside the 4,800-token budget,
- lifts overall recall from 19/30 to **23/30**, the best number recorded,
- lifts trace from 1/5 to 3/5.

That last one matters: **trace reaches 3/5 — the level predicted for BM25 — by
deleting text rather than adding a retriever.** The header was noise competing
with content for both budget and embedding mass.

The effect is specific to split corpora. On whole-file chunking, where the
header appears once per file rather than once per fragment, stripping it makes
things slightly *worse* (12/30 → 10/30): with one chunk per file the path is
useful signal, and there is no per-fragment repetition tax to recover.

## Caveat

Like `rrf body-only` in run 4, this configuration was not pre-registered. It
came out of a diagnostic, and 23/30 is a post-hoc best. Both belong in a
held-out re-run before either becomes a headline.
