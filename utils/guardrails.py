"""
Utility: input/output guardrails (length limits, prompt-injection detection,
PII redaction for logs).
"""

import re
from dataclasses import dataclass

from utils import metrics

MAX_QUERY_CHARS = 1000

_INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above) (instructions|prompts?|rules)",
    r"disregard (all |any |the )?(previous|prior|above|system)",
    r"(reveal|show|print|repeat) (your |the )?(system|hidden|developer) (prompt|instructions|message)",
    r"you are now (?!able)",
    r"\bjailbreak\b",
    r"\bDAN mode\b",
    r"act as (an? )?(unrestricted|unfiltered)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

_PII_RULES = [
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "[EMAIL]"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[CARD]"),
    (re.compile(r"(?i)(password|passwd|pwd|token|api[_ -]?key|secret)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"\b\+?\d[\d -]{8,}\d\b"), "[PHONE]"),
]


@dataclass
class GuardResult:
    allowed: bool
    text: str
    reason: str = ""
    message: str = ""


def redact_pii(text: str) -> str:
    """Mask emails, card numbers, phone numbers and credentials (for logging)."""
    for rx, repl in _PII_RULES:
        text = rx.sub(repl, text)
    return text


def check_input(text: str) -> GuardResult:
    """Validate user input; strips control characters and truncates overlong text."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "").strip()
    if _INJECTION_RE.search(cleaned):
        metrics.incr("guardrail.injection_blocked")
        return GuardResult(
            False, cleaned, "prompt_injection",
            "I can't process that request. Please describe your IT issue and I'll help.",
        )
    if len(cleaned) > MAX_QUERY_CHARS:
        metrics.incr("guardrail.truncated")
        cleaned = cleaned[:MAX_QUERY_CHARS]
    return GuardResult(True, cleaned)

_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ID_RE = re.compile(r"\b(?:KB|TKT|EMP)-?\d+\b", re.IGNORECASE)
_PHONE_EXT_RE = re.compile(r"\bext\.?\s*\d{3,5}\b", re.IGNORECASE)


def _facts(text: str) -> set[str]:
    found = set()
    for rx in (_URL_RE, _EMAIL_RE, _ID_RE, _PHONE_EXT_RE):
        found.update(m.group(0).lower().rstrip(".,;") for m in rx.finditer(text))
    return found


def check_grounding(answer: str, *context: str) -> tuple[bool, list[str]]:
    """
    Hallucination check: every URL, email, article/ticket/employee ID and
    extension quoted in `answer` must appear in the supplied context
    (tool output, system prompt, user message). Returns (grounded, unsupported).
    """
    allowed = set()
    for c in context:
        allowed |= _facts(c or "")
    unsupported = sorted(f for f in _facts(answer or "") if f not in allowed)
    metrics.incr("guardrail.grounding_checks")
    if unsupported:
        metrics.incr("guardrail.hallucination_detected")
        metrics.log_event("hallucination_detected", unsupported=unsupported[:10])
    return (not unsupported, unsupported)
