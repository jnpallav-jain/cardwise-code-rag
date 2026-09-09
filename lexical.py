"""
BM25 lexical retrieval and reciprocal rank fusion.

Dense embeddings blur identifiers: `CardWiseComponents` and `Components` sit
close in vector space, and a call site that merely mentions the symbol looks
no more relevant than a file about the same topic. Trace questions ("what
calls X", "where is Y used") are exactly the case where the literal token is
the answer, and they score 0-1 of 5 on dense retrieval.

Tokenization is the whole game for code. `CardWiseComponents` must produce
{cardwisecomponents, card, wise, components} or a query for "CardWiseComponents"
will never match a file that writes it in another case. The identifier is kept
whole *and* split, so exact matches still outrank partial ones.
"""

import re

from rank_bm25 import BM25Okapi

_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+|[0-9]+")


def tokenize(text: str) -> list[str]:
    """Whole identifier plus its camelCase / snake_case parts, all lowercased."""
    out = []
    for raw in _SPLIT.split(text):
        if not raw:
            continue
        low = raw.lower()
        out.append(low)
        parts = _CAMEL.findall(raw)
        if len(parts) > 1:
            out.extend(p.lower() for p in parts)
    return out


class Bm25Index:
    def __init__(self, texts: list[str]):
        self.bm25 = BM25Okapi([tokenize(t) for t in texts])

    def scores(self, query: str):
        return self.bm25.get_scores(tokenize(query))


def rrf(rankings: list[list[int]], k: int = 60, n: int = 0) -> list[int]:
    """
    Reciprocal rank fusion. Each ranking is a list of document indices, best
    first. A document's fused score is sum(1 / (k + rank)) across rankings,
    with rank 1-based. k=60 is the standard constant from Cormack et al.;
    it damps the top of each list so one retriever cannot dominate.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, 1):
            fused[doc] = fused.get(doc, 0.0) + 1.0 / (k + rank)
    return [d for d, _ in sorted(fused.items(), key=lambda kv: -kv[1])]
