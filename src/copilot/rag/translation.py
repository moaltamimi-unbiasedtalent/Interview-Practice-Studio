"""Advanced query translation: understand → rewrite → multi-query → filters.

Before retrieval, the user query passes through a small structured
query-understanding stage that:

* classifies intent (see ``constants.QUERY_INTENTS``);
* decides whether retrieval is needed at all;
* rewrites an ambiguous query into a clearer retrieval query (intent preserved,
  no new facts);
* generates 2–4 alternate retrieval queries for broad questions;
* infers *safe, whitelisted* metadata filters (never arbitrary DB code);
* produces a short, user-safe explanation (never chain-of-thought).

The LLM output is validated with Pydantic (:class:`TranslatedQuery`). Any
failure — no model, an exception, or malformed output — falls back to a
deterministic heuristic so translation never breaks the chat.
"""

from __future__ import annotations

import json
import re

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.models import TranslatedQuery
from src.copilot.rag.responder import Responder, build_openrouter_responder

__all__ = ["QueryTranslator", "sanitize_filters", "heuristic_translation"]

_MAX_EXPLANATION_CHARS = 240

_SYSTEM_PROMPT = """You are the query-understanding stage of a career knowledge \
assistant. Analyse the user's query and return STRICT JSON only — no prose, no \
markdown, no code fences.

Return an object with exactly these keys:
- "intent": one of {intents}
- "retrieval_required": boolean (false only for greetings/small talk or requests \
that need no knowledge base)
- "rewritten_query": a single clearer retrieval query that preserves the user's \
intent. Do NOT add facts, numbers or claims the user did not imply.
- "alternate_queries": an array of 0 to {max_alt} additional retrieval queries \
covering different phrasings/angles for broad questions; use fewer (or none) for \
narrow questions. Do not repeat the rewritten query.
- "metadata_filters": an object using ONLY these fields when clearly implied: \
{filter_fields}. Use exact allowed values only; otherwise return an empty object.
- "explanation": one short, user-safe sentence describing what you changed. No \
step-by-step reasoning.

Allowed document_type values: {doc_types}."""


def _user_prompt(query: str) -> str:
    return f'User query: "{query}"\n\nReturn the JSON object now.'


def sanitize_filters(raw: object) -> dict:
    """Keep only whitelisted equality filters with allowed values."""
    if not isinstance(raw, dict):
        return {}
    clean: dict = {}
    for field, allowed in constants.ALLOWED_FILTER_FIELDS.items():
        if field not in raw:
            continue
        value = raw[field]
        if not isinstance(value, (str, int, float, bool)):
            continue
        if allowed is not None and value not in allowed:
            continue
        clean[field] = value
    return clean


def _clean_alternates(
    alternates: object, *, rewritten: str, original: str, limit: int
) -> list[str]:
    if not isinstance(alternates, list):
        return []
    seen = {rewritten.strip().lower(), original.strip().lower()}
    result: list[str] = []
    for item in alternates:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _valid_intent(value: object) -> str:
    if isinstance(value, str) and value in constants.QUERY_INTENTS:
        return value
    return constants.DEFAULT_INTENT


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from model text (tolerates code fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in translation output")
    return json.loads(text[start : end + 1])


# --- Heuristic fallback ------------------------------------------------------

_SMALLTALK_RE = re.compile(
    r"^(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening)|"
    r"who are you|what can you do)\b",
    re.IGNORECASE,
)
_INTENT_KEYWORDS = [
    ("interview_preparation", ("interview", "behavioural", "behavioral", "star method")),
    ("job_description_analysis", ("job description", "this jd", "job posting", "this posting")),
    ("candidate_comparison", ("compare", " vs ", "versus", "candidate")),
    ("preparation_planning", ("prepare", "preparation plan", "prep plan", "study plan",
                              "roadmap", "learning plan", "30-day", "30 day")),
    ("skill_research", ("skill", "skills", "competenc", "learn", "capabilit")),
    ("role_research", ("role", "responsibilities", "occupation", "what does a", "duties")),
]


def heuristic_translation(query: str) -> TranslatedQuery:
    """Deterministic, LLM-free translation used as the fallback."""
    query = query.strip()
    lowered = query.lower()

    if _SMALLTALK_RE.match(lowered):
        return TranslatedQuery(
            original_query=query,
            rewritten_query=query,
            intent="smalltalk",
            retrieval_required=False,
            explanation="Treated as small talk; no knowledge-base search needed.",
            strategy="heuristic",
        )

    intent = constants.DEFAULT_INTENT
    for candidate, keywords in _INTENT_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            intent = candidate
            break
    if intent == constants.DEFAULT_INTENT and query.endswith("?"):
        intent = "factual_career"

    filters: dict = {}
    if intent == "skill_research":
        filters = {"document_type": "skills"}
    elif intent == "interview_preparation":
        filters = {"document_type": "interview_guidance"}

    return TranslatedQuery(
        original_query=query,
        rewritten_query=query,
        intent=intent,
        retrieval_required=True,
        metadata_filters=filters,
        explanation="Used the query as-is (automatic understanding unavailable).",
        strategy="heuristic",
    )


class QueryTranslator:
    """LLM-backed query translation with a deterministic fallback."""

    def __init__(
        self,
        *,
        config: CopilotConfig | None = None,
        responder: Responder | None = None,
        enabled: bool = True,
        max_alternates: int = constants.MAX_ALTERNATE_QUERIES,
        model: str | None = None,
    ) -> None:
        self.config = config
        self._responder = responder
        self.enabled = enabled
        self.max_alternates = max_alternates
        self.model = model

    def _system_prompt(self) -> str:
        return _SYSTEM_PROMPT.format(
            intents=", ".join(constants.QUERY_INTENTS),
            max_alt=self.max_alternates,
            filter_fields=", ".join(constants.ALLOWED_FILTER_FIELDS),
            doc_types=", ".join(constants.KNOWN_DOCUMENT_TYPES),
        )

    def _resolve_responder(self) -> Responder | None:
        if self._responder is not None:
            return self._responder
        if self.config is None:
            return None
        try:
            return build_openrouter_responder(self.config, model=self.model, temperature=0.0)
        except Exception:
            return None

    def translate(self, query: str) -> TranslatedQuery:
        """Translate ``query``; fall back to a heuristic on any failure."""
        query = (query or "").strip()[: constants.MAX_QUERY_CHARS]
        if not query:
            raise ValueError("query must not be empty")
        if not self.enabled:
            return heuristic_translation(query)

        responder = self._resolve_responder()
        if responder is None:
            return heuristic_translation(query)

        try:
            messages = [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": _user_prompt(query)},
            ]
            reply = responder(messages)
            return self._parse(query, reply.content)
        except Exception:
            # Malformed output, network error, bad JSON, validation error, …
            return heuristic_translation(query)

    def _parse(self, query: str, content: str) -> TranslatedQuery:
        raw = _extract_json(content)

        rewritten = raw.get("rewritten_query")
        if not isinstance(rewritten, str) or not rewritten.strip():
            rewritten = query
        rewritten = rewritten.strip()

        intent = _valid_intent(raw.get("intent"))
        retrieval_required = bool(raw.get("retrieval_required", True))
        if intent in constants.NO_RETRIEVAL_INTENTS:
            retrieval_required = False

        alternates = _clean_alternates(
            raw.get("alternate_queries"),
            rewritten=rewritten,
            original=query,
            limit=self.max_alternates,
        )

        explanation = raw.get("explanation")
        if not isinstance(explanation, str):
            explanation = ""
        explanation = " ".join(explanation.split())[:_MAX_EXPLANATION_CHARS]

        return TranslatedQuery(
            original_query=query,
            rewritten_query=rewritten,
            alternate_queries=alternates,
            intent=intent,
            retrieval_required=retrieval_required,
            metadata_filters=sanitize_filters(raw.get("metadata_filters")),
            explanation=explanation,
            strategy="llm",
        )
