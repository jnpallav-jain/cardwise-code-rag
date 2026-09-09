# Run 4 — BM25 and reciprocal rank fusion

Chunking fixed at uniform-400. Only retrieval varies. Predictions in
`PREDICTIONS.md` were committed (4ba6261) before any BM25 code existed.

| config          |    @5 | @4,800 tok | trace @5 / @bud | cross @5 / @bud |
|-----------------|-------|------------|-----------------|-----------------|
| dense (baseline)| 16/30 |      19/30 |     0/5 · 1/5   |     3/5 · 4/5   |
| bm25            |  3/30 |       8/30 |     1/5 · 1/5   |     0/5 · 0/5   |
| bm25 body-only  |  4/30 |       5/30 |     0/5 · 0/5   |     0/5 · 0/5   |
| rrf             | 15/30 |      19/30 |     1/5 · 1/5   |     0/5 · 3/5   |
| **rrf body-only** | 12/30 | **21/30** |   0/5 · **4/5** |     1/5 · 3/5   |

## Scorecard against the predictions

**Pallav — "trace goes from 15% to above 60%": correct under one metric,
wrong under the other.** At equal context, trace goes 1/5 → 4/5, i.e. 20% →
80%. At recall@5 it goes 0/5 → 0/5. The prediction was right about the
mechanism and right about the size of the effect; it was silent on which
metric, and the two disagree completely.

**Claude — mixed.**
- "Trace 3/5 or 4/5" — correct at budget (4/5), wrong at @5 (0/5).
- "Overall 19–22/30" — correct at budget (21/30), wrong at @5 (12/30, down
  from 16).
- "Cross-platform does not improve and may worsen" — correct. 4/5 → 3/5 at
  budget, 3/5 → 1/5 at @5.
- "Tokenization is the risk" — **wrong**. The tokenizer works
  (`CardWiseComponents` → `{cardwisecomponents, card, wise, components}`).
- "The `# File:` header is poisoning BM25" — **wrong**, and worth recording
  as a failed hypothesis. Stripping it moved BM25 from 3/30 to 4/30.

## What actually happened

**BM25 alone is catastrophic here: 3/30.** Not a tuning problem. The corpus
name is inside every path, so `card` appears in 272 of 334 chunks and `wise`
in 160 — the IDF term that should make identifiers discriminating is destroyed
by a codebase whose every file is named after the product. Natural-language
questions ("Where is the logic that picks the best card for a purchase?")
supply mostly common words, and BM25 has nothing rare to lock onto.

**But BM25 contributes something dense retrieval cannot.** Fused, trace at
equal context goes 1/5 → 4/5. On Q22 ("Which screens read from AppState?")
BM25 alone returns AppState.kt, SettingsScreen.kt, WalletScreen.kt and
HomeScreen.kt in its top five — all four expected files, which dense retrieval
never assembles. A 10%-accuracy retriever still carried the signal that the
77%-accuracy one was missing.

**The two metrics invert the conclusion.** RRF is worse at recall@5 (12 vs 16)
and better at equal context (21 vs 19). Fusion spreads probability across more
distinct files while pushing any single best chunk down the ranking; with five
chunk slots that dilutes, and with a 4,800-token budget (~13 chunks at this
size) it accumulates. Reporting either number alone would support the opposite
conclusion.

**21/30 at equal context is the best result recorded so far**, against 19/30
for dense and 12/30 for whole-file chunking in run 3.

## Caveat

`rrf body-only` was not a pre-registered configuration — it came out of a
failed diagnosis of BM25's score. It is reported here as the best number, but
it was selected after seeing results, which is exactly the thing the frozen
question set exists to prevent. Treat 21/30 as promising rather than measured,
and re-run it against held-out questions before it goes in a README.
