# Predictions, recorded before the run

Written before any BM25 code existed, so the numbers below cannot have been
tuned toward. Committed separately from the results for the same reason.

## Run 4 — BM25 + reciprocal rank fusion

**Setup.** Chunking fixed at uniform-400. Only retrieval changes: dense
(voyage-code-4) alone, BM25 alone, and RRF over both. Same 30 frozen
questions, same three metrics.

**Baseline being beaten** (uniform-400, dense-only, from `results.json`):

| section        | recall@5 | recall@4,800 tok |
|----------------|----------|------------------|
| locate         | 10/10    | 10/10            |
| explain        |  3/10    |  4/10            |
| trace          |  0/5     |  1/5             |
| cross-platform |  3/5     |  4/5             |
| **overall**    | **16/30**| **19/30**        |

### Pallav's prediction (on record)

> Trace goes from 15% to above 60%.

i.e. trace recall rises from 0–1 of 5 to **at least 3 of 5**. Rationale:
trace questions ("what calls X", "where is Y used") are lexical — the answer
is the file containing the literal identifier — and lexical search has never
been tested here.

### Claude's prediction (on record)

- **Trace: 3/5 or 4/5.** Agreeing with the direction. Q21, Q22 and Q25 all
  turn on a literal symbol (`RecommendationEngine`, `AppState`,
  `CardWiseComponents`) appearing in the calling file, which is exactly what
  BM25 scores and what a dense embedding blurs.
- **Overall recall@5: 19–22/30**, up from 16.
- **The cross-platform twin problem does not improve, and may worsen.**
  `SettingsScreen.kt` and `SettingsView.swift` share most of their
  identifiers, so BM25 will rank both highly too. This failure mode is a
  corpus property, not a retrieval-mode property.
- **Locate stays at 10/10** — already at ceiling, no headroom.
- **Explain improves least** (3/10 → 3–5/10); those questions are conceptual,
  where dense retrieval is supposed to be the stronger half.
- **Where I could be wrong:** if BM25's tokenizer does not split camelCase and
  snake_case, `CardWiseComponents` never matches `cardWiseComponents` at a
  call site and trace stays near zero. Tokenization, not the algorithm, is the
  risk.

### Falsification

If trace lands at 2/5 or below, the prediction is wrong and that is the more
interesting result: it would mean these questions fail for a reason neither
lexical nor dense retrieval addresses — most likely that the answer files
never mention the symbol in a form either method can match.
