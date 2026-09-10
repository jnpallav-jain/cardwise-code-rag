# Setup

All work happens in a project venv. Phoenix pulls in `protobuf>=7` and a newer
`wrapt`, which conflict with other tools if installed globally.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run everything with `.venv/bin/python`, not `python3`:

```bash
.venv/bin/python ingest.py ~/my-git/CardWise      # whole-file corpus
.venv/bin/python chunk.py --mode hybrid  --target 1200
.venv/bin/python chunk.py --mode uniform --target 400

.venv/bin/python embed.py corpus/chunks.jsonl     # needs VOYAGE_API_KEY
.venv/bin/python score.py                         # all arms, both metrics
.venv/bin/python score.py --arm uniform-400 --retrieval rrf --strip-header
```

Ask it a question outside the eval set:

```bash
.venv/bin/python ask.py "How does the recommendation engine rank cards?"
.venv/bin/python ask.py --show-chunks "What writes to the cards table?"
```

The API key goes in `.env` (gitignored), read by `embed.py`:

```
VOYAGE_API_KEY=...
```

Tracing, optional. Start the collector first, then pass `--trace`:

```bash
.venv/bin/python -m phoenix.server.main serve     # http://localhost:6006
.venv/bin/python score.py --trace
```

## Corpus provenance

The corpus is built from a working tree, not a pinned commit, so
`git -C <repo> rev-parse HEAD` should be recorded alongside any numbers.
The committed vectors were built before CardWise commit c7cccfe (which
untracked IDE state and edited .gitignore); re-running ingest today yields a
42-token difference in one file. Immaterial to the results, but it is the
reason the token totals move slightly between runs.
