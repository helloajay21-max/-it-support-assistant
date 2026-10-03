"""
Tool 1: Knowledge Search
Hybrid retrieval over the local IT knowledge base:
  * BM25 (lexical)
  * Weighted field match (keywords / title / category)
  * Fuzzy semantic match (character n-gram TF-IDF cosine + synonym expansion)
The ranked lists are merged with Reciprocal Rank Fusion (RRF) and results are
returned with citations. Every search is guarded, logged and recorded in utils.metrics.
"""

import json
import math
import os
import re
import uuid
from collections import Counter
from typing import Any

from langchain_core.tools import tool

from utils import metrics
from utils.guardrails import check_input, redact_pii
from utils.logger import get_logger

logger = get_logger(__name__)

KB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base.json")

RRF_K = int(os.getenv("RRF_K", "60"))
TOP_K = int(os.getenv("KB_TOP_K", "3"))
# Weight per retriever in the fusion
RRF_WEIGHTS = {"bm25": 1.0, "field": 1.0, "semantic": 0.8}
# Minimum fused score (relative to a rank-1 hit in every retriever) to be returned
MIN_RELATIVE_SCORE = 0.25
MIN_STRENGTH = 0.35  # secondary results must be reasonably close to the best match

STOP_WORDS = {
    "i", "my", "the", "a", "an", "is", "it", "to", "how", "do", "can", "please",
    "me", "help", "need", "want", "what", "when", "where", "why", "has", "have",
    "been", "not", "working", "issue", "problem", "with", "for", "and", "or",
}

SYNONYMS = {
    "wifi": ["wireless", "network", "internet"],
    "internet": ["network", "wifi"],
    "pc": ["laptop", "computer"],
    "computer": ["laptop"],
    "mail": ["email", "outlook"],
    "email": ["outlook", "mail"],
    "passwd": ["password"],
    "pwd": ["password"],
    "login": ["signin", "password", "account"],
    "locked": ["lockout", "password"],
    "slow": ["performance", "lag"],
    "printer": ["print", "printing"],
}

_index_cache: dict[str, Any] = {"mtime": None, "index": None}


def _load_knowledge_base() -> list[dict]:
    """Load the knowledge base from JSON file."""
    try:
        with open(KB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Knowledge base file not found at: %s", KB_PATH)
        return []
    except json.JSONDecodeError as e:
        logger.error("Failed to parse knowledge base JSON: %s", e)
        return []


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _ngrams(tokens: list[str], n: int = 3) -> list[str]:
    grams = []
    for tok in tokens:
        padded = f"#{tok}#"
        if len(padded) <= n:
            grams.append(padded)
        else:
            grams.extend(padded[i:i + n] for i in range(len(padded) - n + 1))
    return grams


def _expand(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for t in tokens:
        expanded.update(SYNONYMS.get(t, []))
    return expanded


class _Index:
    """In-memory index built once per knowledge-base version."""

    def __init__(self, articles: list[dict]):
        self.articles = articles
        self.docs = []
        for a in articles:
            title = _tokenize(a.get("title", ""))
            kws = _tokenize(" ".join(a.get("keywords", [])))
            content = _tokenize(a.get("content", ""))
            # Title and keywords are repeated to up-weight them in BM25
            self.docs.append(title * 3 + kws * 2 + content)
        n = len(self.docs)
        self.avgdl = (sum(len(d) for d in self.docs) / n) if n else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d) for d in self.docs]

        gram_docs = [Counter(_ngrams(d)) for d in self.docs]
        gdf: Counter = Counter()
        for g in gram_docs:
            gdf.update(g.keys())
        self.gidf = {g: math.log((1 + n) / (1 + c)) + 1 for g, c in gdf.items()}
        self.gvecs = [self._weigh(g) for g in gram_docs]

    def _weigh(self, grams: Counter) -> dict[str, float]:
        vec = {g: (1 + math.log(c)) * self.gidf.get(g, 1.0) for g, c in grams.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {g: v / norm for g, v in vec.items()}

    def bm25(self, query_tokens: set[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
        scores = []
        for tf, doc in zip(self.tf, self.docs):
            s = 0.0
            for t in query_tokens:
                f = tf.get(t, 0)
                if not f:
                    continue
                denom = f + k1 * (1 - b + b * len(doc) / (self.avgdl or 1))
                s += self.idf.get(t, 0.0) * f * (k1 + 1) / denom
            scores.append(s)
        return scores

    def field(self, query_tokens: set[str]) -> list[float]:
        scores = []
        for a in self.articles:
            kws = {w for k in a.get("keywords", []) for w in _tokenize(k)}
            title = set(_tokenize(a.get("title", "")))
            content = set(_tokenize(a.get("content", "")))
            s = len(query_tokens & kws) * 5 + len(query_tokens & title) * 3 + len(query_tokens & content)
            if a.get("category", "").lower() in query_tokens:
                s += 4
            scores.append(float(s))
        return scores

    def semantic(self, query_tokens: set[str]) -> list[float]:
        qvec = self._weigh(Counter(_ngrams(sorted(query_tokens))))
        return [sum(w * dv.get(g, 0.0) for g, w in qvec.items()) for dv in self.gvecs]


def _get_index() -> "_Index | None":
    try:
        mtime = os.path.getmtime(KB_PATH)
    except OSError:
        mtime = None
    if _index_cache["index"] is None or _index_cache["mtime"] != mtime:
        articles = _load_knowledge_base()
        if not articles:
            return None
        _index_cache["index"] = _Index(articles)
        _index_cache["mtime"] = mtime
    return _index_cache["index"]


def _rank(scores: list[float], min_score: float = 0.0) -> list[int]:
    return sorted((i for i, s in enumerate(scores) if s > min_score), key=lambda i: scores[i], reverse=True)


def reciprocal_rank_fusion(rankings: dict[str, list[int]], weights: dict[str, float] | None = None,
                           k: int = RRF_K) -> list[tuple[int, float, dict[str, int]]]:
    """
    Fuse ranked lists: score(d) = sum_r w_r / (k + rank_r(d)), rank starting at 1.
    Returns (doc_index, fused_score, {retriever: rank}) sorted by score desc.
    """
    fused: dict[int, float] = {}
    ranks: dict[int, dict[str, int]] = {}
    for name, order in rankings.items():
        w = (weights or {}).get(name, 1.0)
        for pos, doc in enumerate(order, start=1):
            fused[doc] = fused.get(doc, 0.0) + w / (k + pos)
            ranks.setdefault(doc, {})[name] = pos
    return sorted(((d, s, ranks[d]) for d, s in fused.items()), key=lambda x: x[1], reverse=True)


def _snippet(article: dict, terms: set[str], width: int = 160) -> str:
    content = " ".join(article.get("content", "").split())
    low = content.lower()
    pos = min((low.find(t) for t in terms if t in low), default=0)
    start = max(0, pos - 40)
    snip = content[start:start + width].strip()
    return ("…" if start else "") + snip + ("…" if start + width < len(content) else "")


def hybrid_search(query: str, top_k: int = TOP_K) -> dict[str, Any]:
    """Run hybrid retrieval and return structured results."""
    index = _get_index()
    if index is None:
        return {"status": "unavailable", "results": []}

    raw_tokens = set(_tokenize(query)) - STOP_WORDS
    if not raw_tokens:
        return {"status": "no_terms", "results": []}
    tokens = _expand(raw_tokens)

    bm25 = index.bm25(tokens)
    sem = index.semantic(tokens)
    rankings = {
        "bm25": _rank(bm25),
        "field": _rank(index.field(tokens)),
        "semantic": _rank(sem, min_score=0.15),
    }
    top_bm25 = max(bm25) or 1.0
    fused = reciprocal_rank_fusion(rankings, RRF_WEIGHTS)
    max_possible = sum(w / (RRF_K + 1) for w in RRF_WEIGHTS.values())

    results = []
    for doc, score, ranks in fused:
        rel = score / max_possible
        if rel < MIN_RELATIVE_SCORE:
            break
        # RRF is rank-only; blend in absolute signal so weak matches get low confidence
        strength = 0.6 * (bm25[doc] / top_bm25) + 0.4 * min(sem[doc] / 0.5, 1.0)
        if results and strength < MIN_STRENGTH:
            continue
        art = index.articles[doc]
        results.append({
            "article": art,
            "rrf_score": round(score, 5),
            "confidence": round(min(rel, 1.0) * min(strength + 0.2, 1.0), 3),
            "ranks": ranks,
            "matched_terms": sorted(raw_tokens & set(index.docs[doc])),
        })
        if len(results) >= top_k:
            break
    return {"status": "ok" if results else "no_results", "results": results}


@tool
def knowledge_search(query: str) -> str:
    """
    Search the IT knowledge base for articles relevant to the user's query.
    Use this tool when the user asks a how-to question, requests troubleshooting
    guidance, or wants information about IT policies and procedures.

    Args:
        query: The user's question or topic to search for.

    Returns:
        Relevant knowledge base article content with citations, or a message
        indicating no results were found.
    """
    request_id = uuid.uuid4().hex[:8]
    metrics.incr("kb.search.total")

    if not query or not query.strip():
        metrics.incr("kb.search.invalid")
        return "Error: Search query cannot be empty."

    guard = check_input(query)
    if not guard.allowed:
        metrics.incr("kb.search.blocked")
        metrics.log_event("kb_search_blocked", request_id=request_id, reason=guard.reason)
        return guard.message
    query = guard.text

    with metrics.timed("kb.search.latency") as t:
        outcome = hybrid_search(query)

    status = outcome["status"]
    results = outcome["results"]
    metrics.log_event(
        "kb_search",
        request_id=request_id,
        query=redact_pii(query)[:200],
        status=status,
        latency_ms=round(t["ms"], 2),
        hits=[{"id": r["article"]["article_id"], "rrf": r["rrf_score"],
               "conf": r["confidence"], "ranks": r["ranks"]} for r in results],
    )

    if status == "unavailable":
        metrics.incr("kb.search.error")
        return "Error: Knowledge base is currently unavailable. Please contact IT helpdesk directly."
    if status == "no_terms":
        metrics.incr("kb.search.invalid")
        return "Please provide more specific search terms to find relevant articles."
    if status == "no_results":
        metrics.incr("kb.search.miss")
        return (
            "No relevant knowledge base articles found for your query. "
            "Please try different keywords or contact IT helpdesk at helpdesk@techcorp.com / ext. 4357."
        )

    metrics.incr("kb.search.hit")
    top = results[0]
    art = top["article"]
    result = (
        f"📚 **Knowledge Base Article Found** (confidence: {top['confidence']:.0%})\n\n"
        f"**Article ID:** {art['article_id']}\n"
        f"**Category:** {art['category']}\n"
        f"**Title:** {art['title']}\n\n"
        f"**Instructions:**\n{art['content']}"
    )

    if len(results) > 1:
        result += "\n\n---\n📎 **Related Articles:**"
        for r in results[1:]:
            a = r["article"]
            result += f"\n- {a['title']} [{a['article_id']}] — *ask me about '{a['title']}' for details.*"

    result += "\n\n---\n🔖 **Sources:**"
    for n, r in enumerate(results, start=1):
        a = r["article"]
        terms = ", ".join(r["matched_terms"]) or "semantic match"
        result += (
            f"\n[{n}] {a['article_id']} · {a['category']} · {a['title']} "
            f"(relevance {r['confidence']:.0%}; matched: {terms})"
        )
        if n == 1:
            result += f"\n    > {_snippet(a, set(r['matched_terms']))}"

    logger.info("Knowledge search %s returned %d article(s); top=%s", request_id, len(results), art["article_id"])
    return result

