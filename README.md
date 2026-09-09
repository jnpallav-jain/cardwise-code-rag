# cardwise-code-rag

Retrieval-augmented search over a private multi-platform codebase — Kotlin,
Swift and SQL — evaluated on thirty frozen questions against a long-context
baseline.

**Retrieval accuracy varied 5× by question type, and the fix wasn't chunking.**
Finding a file scored 100%. Tracing what calls it scored 20%. Three chunking
strategies moved that spread by nothing worth reporting; deleting 27 tokens of
metadata I had added to every chunk moved trace from 20% to 60%.

---

## Results

Thirty questions in four categories. A question passes when every file the
answer requires is retrieved (or, end to end, cited). Retrieval arms are
compared at an equal **4,800-token budget**, because counting chunks instead
lets a whole-file arm quietly read 2.6× more text than a split one.

| approach | overall | locate | explain | trace | cross-platform |
|---|---|---|---|---|---|
| long-context (112,779 tok/question) | **25/30** | 100% | 80% | 60% | 80% |
| RAG end-to-end (~4,600 tok/question) | **19/30** | 100% | 50% | 20% | 60% |
| — retrieval only, best config | 23/30 | 100% | 60% | 60% | 80% |
| — retrieval only, with header | 19/30 | 100% | 40% | 20% | 80% |
| — retrieval only, whole-file chunks | 12/30 | 90% | 20% | 0% | 20% |

Long-context wins — while reading **23× the context per question**. That ratio,
not the accuracy column, is the argument for retrieval.

## What actually mattered

**Question type, by a wide margin.** Locate questions are at ceiling in every
configuration. Trace questions ("what calls the recommendation engine?") span
0–60% depending on settings that have nothing to do with how text is split.

**A metadata header I added to help.** Every chunk carried a `# File: <path>`
line: 8,913 tokens across 334 chunks, repeated on every fragment of every split
file. Removing it raised overall recall from 19/30 to 23/30 and trace from 20%
to 60% — the same improvement predicted for adding a lexical retriever,
achieved by deleting text.

**Chunking barely mattered.** Whole-file, hybrid and uniform-400 scored 16, 17
and 16 out of 30 under the metric the eval specified. At equal context they
separate — 12, 17, 19 — but that gap is mostly the metric, not the strategy.

**The dominant failure mode isn't retrieval at all.** This codebase implements
the same features twice, in Kotlin and Swift. `SettingsScreen.kt` and
`SettingsView.swift` are near-translations, so the twin scores almost
identically to the target and crowds it out. No chunk size fixes that; it needs
platform filtering or a reranker.

## What didn't work

**BM25 scored 3/30 alone.** The corpus is named after its product, so `card`
appears in 272 of 334 chunks — the IDF signal that should make identifiers
discriminating is destroyed. Fused with dense retrieval it still helped trace
(1/5 → 4/5 at equal context): a 10%-accuracy retriever fixing what a
53%-accuracy one missed.

**Two recorded predictions were wrong.** Both are in
[`eval/PREDICTIONS.md`](eval/PREDICTIONS.md), committed before the code that
tested them existed.

## The part worth reading

**Every measurement bug found on this project made the result look better than
it was.**

- `max_tokens` truncated answers before the citation line — scored as zero
  citations, indistinguishable from a wrong answer.
- A thinking block consumed an entire token budget, returning no text at all.
  Same silent zero.
- tree-sitter cannot parse `ON CONFLICT ... DO UPDATE SET`, which appears in
  every migration here, so "structural" SQL chunking was mechanical slicing
  wearing a parser's name.
- Cutting only at top-level nodes turned a one-class Swift file into fixed-size
  chunks — structural chunking that wasn't.
- Comparing retrieval recall against citation coverage flattered RAG by 4
  questions, because recall measures whether a file was *available* and
  coverage measures whether it was *used*.

The eval set was frozen before any run, and the prose cells were resolved into
concrete paths in [`eval/expected.json`](eval/expected.json) without editing
the frozen file.

## Caveats

- **n=30.** A one-question difference is noise. Only the 12-vs-19 and 19-vs-25
  gaps are worth defending.
- **The long-context baseline is non-deterministic.** Two runs disagreed on
  three questions. The retrieval arms are exactly reproducible; this isn't.
- **Two best-performing configurations were found post-hoc** (`rrf body-only`,
  `no-header`) and are marked as such. They need held-out questions.
- **The baseline only exists because this corpus is small.** At 113k tokens it
  fits one prompt. At 10× it doesn't, and retrieval stops being optional.

## Layout

```
ingest.py       corpus from a git repo, one record per file
chunk.py        stage-2 splitting: hybrid and uniform modes
embed.py        voyage-code-4, cached per arm
lexical.py      BM25 with a code-aware tokenizer, plus RRF
score.py        retrieval scoring, three metrics
generate.py     end-to-end RAG: retrieve, answer, cite
longcontext.py  the baseline: whole corpus, one prompt
tracing.py      Phoenix spans for every retrieval
eval/           frozen questions, resolved expectations, predictions, results
```

Setup and commands: [SETUP.md](SETUP.md). Per-run write-ups:
[run 4](eval/RESULTS-run4.md), [run 5](eval/RESULTS-run5.md),
[run 6](eval/RESULTS-run6.md).
