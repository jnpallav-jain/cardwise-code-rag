# cardwise-code-rag

Retrieval-augmented search over a private multi-platform codebase — Kotlin,
Swift and SQL — evaluated on thirty frozen questions against a long-context
baseline.

---

## 1. The headline

**Pasting the entire repository into one prompt beat the RAG pipeline, 25/30
against 19/30, while reading 25× more context per question.**

| approach | score | context per question |
|---|---|---|
| long-context (whole corpus, no retrieval) | **25/30** | 112,779 tokens |
| RAG end-to-end (retrieve → answer → cite) | **19/30** | 4,528 tokens |

Both are scored identically: the answer must cite every file it needed.

That ratio is the real result. Retrieval costs 4% of the context and returns
76% of the accuracy — a reasonable trade that the accuracy column alone would
never justify. And it only holds because this corpus is small enough that the
baseline is *available*: 113k tokens fits one prompt, 10× would not, and at
that point retrieval stops being a choice.

So the interesting question was never which retrieval strategy won. All three
chunking strategies landed within one question of each other:

| chunking | recall@5 |
|---|---|
| whole-file | 16/30 |
| hybrid (split only files >1,500 tokens) | 17/30 |
| uniform-400 | 16/30 |

Three weeks of chunking work, one question of difference.

## 2. What did matter: question type

The same retriever, on the same corpus, in the same run:

| question type | example | recall |
|---|---|---|
| **locate** | "Where is the wallet screen on iOS?" | **100%** |
| cross-platform | "How does settings differ between iOS and Android?" | 80% |
| explain | "What settings can a user change, and where are they persisted?" | 40% |
| **trace** | "What calls the recommendation engine on Android?" | **20%** |

**A 5× spread by category — against a 1-question spread across every chunking
strategy tested.** Which question you ask determines the answer's quality far
more than how you slice the corpus.

The mechanism is straightforward once seen. Locate questions have their answer
in one file, and embedding similarity is good at finding one file. Trace
questions require following a reference *between* files — `AppState.kt:221`
calls `repository.recommend()`, which reaches `CardWiseRepository.kt:31`, which
instantiates `RecommendationEngine`. An embedding scores each file
independently. It cannot follow anything.

A second corpus property compounds it: this codebase implements every feature
twice, in Kotlin and Swift. `SettingsScreen.kt` and `SettingsView.swift` are
near-translations, so the twin scores almost identically to the target and
takes its slot. No chunk size fixes that.

## 3. Two results I did not expect

### Removing the file path from every chunk improved retrieval

Each chunk carried a `# File: <path>` header so a chunk retrieved in isolation
would still say what it was. It seemed obviously helpful.

It cost **8,913 tokens across 334 chunks** — 27 tokens repeated on every
fragment of every split file, about 7.4% of the corpus. Deleting it:

| | with header | without |
|---|---|---|
| overall @4,800 tok | 19/30 | **23/30** |
| trace | 20% | **60%** |

Trace tripled by deleting text. That is the same improvement I had predicted
would require adding a whole second retriever.

First I checked the obvious worry — was `locate`'s 100% just filename matching?
Strip every path and it scores **9/10**. One question breaks: "Where is the
Supabase project configured?", where the path genuinely was the answer. The
locate number is real retrieval.

The effect is specific to split corpora. On whole-file chunking the header
appears once per file, carries signal, and removing it makes things *worse*
(12/30 → 10/30).

### BM25 alone scored 3/30

Lexical search should own trace questions — the answer is the file containing
the literal identifier. It scored **3/30**, against 16/30 for dense.

The cause is the corpus itself. Every path contains the product name, so `card`
appears in 272 of 334 chunks and `wise` in 160. The IDF signal that makes an
identifier discriminating is destroyed by a codebase named after its product.
Natural-language questions supply mostly common words, and BM25 has nothing
rare to lock onto.

But it still carried something dense retrieval could not. Fused with RRF, trace
went **1/5 → 4/5** at equal context. On "Which screens read from `AppState`?"
BM25 alone returns all four expected files in its top five — dense never
assembles them. A 10%-accuracy retriever fixing what a 53%-accuracy one missed.

## 4. What I predicted wrong

Predictions were committed in
[`eval/PREDICTIONS.md`](eval/PREDICTIONS.md) (`4ba6261`) **before the code that
tested them existed**. The commit order is checkable in `git log`.

**Prediction 1 — "BM25 will lift trace above 60%."** *Wrong as stated, right by
accident.* BM25 alone left trace at 1/5. Fused with dense it reached 4/5 at
equal context — but at recall@5, the metric actually specified, it stayed at
0/5. The prediction was silent about which metric, and the two metrics
disagreed completely. Being right about the mechanism and wrong about the
measurement is its own lesson.

**Prediction 2 — "The failure is tokenization: BM25 won't split camelCase, so
`CardWiseComponents` will never match a call site."** *Wrong.* The tokenizer
worked correctly on the first attempt —
`CardWiseComponents` → `{cardwisecomponents, card, wise, components}`. The real
cause was IDF collapse, which I had not considered at all.

**Prediction 3 — "The `# File:` header is poisoning BM25."** *Wrong.* A clean,
plausible diagnosis. Stripping the header moved BM25 from 3/30 to 4/30 —
nothing. It did, however, improve *dense* retrieval substantially, which is how
the finding in §3 was found: by testing a wrong hypothesis and reading the
result carefully.

**Prediction 4 — "Long-context will win big on trace, because a model reading
every file can follow a call graph."** *Wrong.* Long-context and the best RAG
arm both scored 3/5 on trace. The gap between them is entirely in `explain`
(80% vs 50%). A model that can see every file did not follow references better;
it combined *facts across* files better.

### The bugs, which all pointed the same way

Every measurement error found on this project made the result look **better**
than it was:

- `max_tokens` truncated answers before the citation line — scored as zero
  citations, indistinguishable from a wrong answer.
- A thinking block consumed an entire 2,048-token budget and returned no text
  at all. Same silent zero.
- tree-sitter cannot parse `ON CONFLICT ... DO UPDATE SET`, present in every
  migration here, so "structural" SQL chunking was mechanical slicing wearing a
  parser's name.
- Cutting only at top-level nodes turned a one-class Swift file into fixed-size
  chunks — structural chunking that wasn't.
- Comparing retrieval recall against citation coverage flattered RAG by four
  questions, because recall measures whether a file was *available* and
  coverage measures whether it was *used*.

That last one is why §1 reports 19/30 and not 23/30.

## 5. Method

**Corpus.** 165 tracked files → 119 indexed, **113,256 tokens** (`o200k_base`,
measured — an early `len(text)//4` estimate was 5% high in aggregate but −28% to
+25% per file, enough to reorder which files got split). 46 files excluded, all
images, IDE state or build tooling; no source file is excluded, and the count
is reconciled in `ingest.py`'s summary.

**Chunking.** `ingest.py` emits one record per file. `chunk.py` splits, in two
modes — `hybrid` (only files over 1,500 tokens) and `uniform` (everything, at a
smaller target). Splits are structural via tree-sitter where the grammar parses,
with a hand-written scanner for SQL and a fixed-size fallback on any parse
error. Every file's fragments are asserted to reconcatenate into the original
byte-for-byte before anything is written.

**Embeddings.** `voyage-code-4`, 1024-dim, `input_type` set asymmetrically for
documents and queries. The vector store is a numpy array — at 119–334 chunks a
vector database earns nothing.

**Eval.** Thirty questions in four categories, **frozen before the first run**.
Ten cells were prose ("wherever persistence lives"); those were resolved into
concrete paths in [`eval/expected.json`](eval/expected.json) *without editing
the frozen file*, each carrying a confidence and a note where the resolution
narrows or extends the original.

**Metrics — three, because the obvious one is not fair.** Counting *chunks*
lets whole-file chunking read 4,759 tokens for its five slots while uniform-400
reads 1,795. So results are reported at recall@5 chunks (as specified), recall@5
*distinct files* (deduped — split arms lost 23 and 45 of 150 slots to repeat
chunks of a file already retrieved), and recall at an equal **4,800-token
budget**. Where they disagree, the disagreement is the finding.

**Reproduce.** See [SETUP.md](SETUP.md). Everything runs from `.venv`; the
corpus is gitignored because it is private source code.

## Caveats

- **n=30.** A one-question difference is noise. Only 12-vs-19 and 19-vs-25 are
  worth defending.
- **The long-context baseline is non-deterministic.** Two runs disagreed on
  three questions. The retrieval arms are exactly reproducible; this is not.
- **Two best-performing configs were found post-hoc** (`rrf body-only`,
  `no-header`). They need held-out questions before they are load-bearing.
- **The corpus is built from a working tree**, not a pinned commit. Any number
  should carry the source repo's HEAD.

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

Per-run write-ups: [run 4 — BM25 and RRF](eval/RESULTS-run4.md),
[run 5 — the path header](eval/RESULTS-run5.md),
[run 6 — long-context](eval/RESULTS-run6.md).
