# Run 6 — long-context baseline

Whole corpus in one prompt, no retrieval. 112,779 tokens, claude-sonnet-5,
each of the 30 frozen questions asked separately, corpus sent as a cached
system block. Scored on the same expected-file sets: did the answer's `CITED:`
line include every expected file?

## Result

| approach                          | overall | locate | explain | trace | cross |
|-----------------------------------|---------|--------|---------|-------|-------|
| **long-context**                  | **25/30** | 10/10 | 8/10   | 3/5   | 4/5   |
| RAG uniform-400 no-header @4,800  | 23/30   | 10/10  | 6/10    | 3/5   | 4/5   |
| RAG uniform-400 @4,800            | 19/30   | 10/10  | 4/10    | 1/5   | 4/5   |
| RAG whole-file @4,800             | 12/30   | 9/10   | 2/10    | 0/5   | 1/5   |

**Long-context wins, by 2 questions over the best RAG configuration.** On a
corpus this size, retrieval is a net loss: the pipeline discards information
the model could otherwise have used.

The margin is smaller than expected. The best RAG arm reaches 23/30 while
reading roughly 4,800 tokens per question; long-context reads 112,779 to score
25/30. That is **23× the context for a 9% relative gain** -- which is the
argument for retrieval, just not the one the accuracy column makes.

## Where the gap actually is

Not trace, and this contradicts the prediction going in. Long-context and the
best RAG arm both score 3/5 on trace. A model that can read every file did not
follow call graphs better than an embedding that reads none of them.

The gap is **explain: 8/10 against 6/10**. Those questions ("what settings can
a user change, and where are they persisted") need several files combined, and
the failure mode is retrieval never surfacing the second file -- not the model
failing to reason over it.

Cross-platform is tied at 4/5, which is the more interesting null result: the
Kotlin/Swift twin problem that dominates retrieval failures does not hurt a
model that sees both files anyway.

## Three measurement bugs, all pointing the same way

1. **`max_tokens=1024`** truncated answers before the `CITED:` line. Fixed by
   putting `CITED:` first and recording `stop_reason`.
2. **`max_tokens=2048`** still failed on Q26: this model emits a `thinking`
   block, and Q26 spent the entire budget thinking, returning no text block at
   all. Scored as zero citations -- indistinguishable from a genuine miss.
3. **A `.env` loader collision** in embed.py: python-dotenv was imported as
   `load_dotenv`, shadowing the hand-written reader; its no-arg form inspects
   the caller's stack frame and fails for scripts on stdin.

All three made the baseline look *worse* than it is, i.e. made RAG look better.
Fixing them moved the result 24/30 → 25/30 and would have moved it further at
1024. Measurement error on this project has consistently favoured the
hypothesis being tested, which is the direction that should worry us.

## The variance caveat

Two runs at different `max_tokens` disagree on **three questions** (Q6, Q20,
Q26), netting 24/30 and 25/30. Q20 passed at 2048 and failed at 4096 with no
truncation in either -- that is sampling noise, not a settings effect.

This baseline is **non-deterministic in a way the retrieval arms are not**.
Cosine similarity over fixed vectors returns identical results every run;
an LLM does not. A single long-context number carries roughly +/-1-2 questions
of noise, so "25 vs 23" is not a reliable ordering on n=30. Report it as a
tie-or-slight-edge, or run it five times and report the mean.
