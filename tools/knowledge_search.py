"""
Tool 1: Knowledge Search
Searches the local IT knowledge base using keyword and semantic matching.
"""

import json
import os
import re
from typing import Any

from langchain_core.tools import tool

from utils.logger import get_logger

logger = get_logger(__name__)

KB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base.json")


def _load_knowledge_base() -> list[dict]:
    """Load and cache the knowledge base from JSON file."""
    try:
        with open(KB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Knowledge base file not found at: %s", KB_PATH)
        return []
    except json.JSONDecodeError as e:
        logger.error("Failed to parse knowledge base JSON: %s", e)
        return []


def _calculate_relevance_score(article: dict, query_tokens: set[str]) -> int:
    """
    Calculate a relevance score for an article given query tokens.
    Higher score = more relevant.
    """
    score = 0
    article_keywords = {kw.lower() for kw in article.get("keywords", [])}
    title_tokens = set(re.findall(r"\w+", article.get("title", "").lower()))
    content_tokens = set(re.findall(r"\w+", article.get("content", "").lower()))
    category = article.get("category", "").lower()

    score += len(query_tokens & article_keywords) * 5
    score += len(query_tokens & title_tokens) * 3
    score += len(query_tokens & content_tokens) * 1
    if category in query_tokens:
        score += 4

    return score


@tool
def knowledge_search(query: str) -> str:
    """
    Search the IT knowledge base for articles relevant to the user's query.
    Use this tool when the user asks a how-to question, requests troubleshooting
    guidance, or wants information about IT policies and procedures.

    Args:
        query: The user's question or topic to search for.

    Returns:
        Relevant knowledge base article content or a message indicating no results found.
    """
    logger.info("Knowledge search called with query: %s", query)

    if not query or not query.strip():
        return "Error: Search query cannot be empty."

    articles = _load_knowledge_base()
    if not articles:
        return "Error: Knowledge base is currently unavailable. Please contact IT helpdesk directly."

    # Tokenize query
    stop_words = {"i", "my", "the", "a", "an", "is", "it", "to", "how", "do", "can", "please",
                  "me", "help", "need", "want", "what", "when", "where", "why", "has", "have",
                  "been", "not", "working", "issue", "problem", "with", "for", "and", "or"}
    query_tokens = set(re.findall(r"\w+", query.lower())) - stop_words

    if not query_tokens:
        return "Please provide more specific search terms to find relevant articles."

    # Score all articles
    scored = []
    for article in articles:
        score = _calculate_relevance_score(article, query_tokens)
        if score > 0:
            scored.append((score, article))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return (
            "No relevant knowledge base articles found for your query. "
            "Please try different keywords or contact IT helpdesk at helpdesk@techcorp.com / ext. 4357."
        )

    # Return top match with full content
    top_score, top_article = scored[0]
    result = (
        f"📚 **Knowledge Base Article Found**\n\n"
        f"**Article ID:** {top_article['article_id']}\n"
        f"**Category:** {top_article['category']}\n"
        f"**Title:** {top_article['title']}\n\n"
        f"**Instructions:**\n{top_article['content']}"
    )

    # Add secondary result if significantly relevant
    if len(scored) > 1 and scored[1][0] >= 3:
        _, second_article = scored[1]
        result += (
            f"\n\n---\n📎 **Related Article:** {second_article['title']} "
            f"(ID: {second_article['article_id']})\n"
            f"*Ask me about '{second_article['title']}' for more details.*"
        )

    logger.info("Knowledge search returned article: %s (score: %d)", top_article["article_id"], top_score)
    return result
