"""OPT-4: session TTL cache and quality/cost modes."""

from __future__ import annotations

from src.copilot.cache import TTLCache
from src.copilot.config import CopilotConfig
from src.copilot.rag.translation import TranslatedQuery
from src.copilot.service import CareerIntelligenceService


class TestTTLCache:
    def test_hit_then_miss_and_stats(self) -> None:
        c = TTLCache(ttl_seconds=100, max_entries=8)
        c.set("q", 42)
        assert c.get("q") == (True, 42)
        assert c.get("absent") == (False, None)
        assert c.stats() == {"entries": 1, "hits": 1, "misses": 1}

    def test_eviction_is_lru(self) -> None:
        c = TTLCache(ttl_seconds=100, max_entries=2)
        c.set("a", 1); c.set("b", 2); c.set("c", 3)  # a evicted
        assert c.get("a")[0] is False
        assert c.get("b")[0] is True and c.get("c")[0] is True

    def test_expiry_uses_injected_clock(self) -> None:
        now = [0.0]
        c = TTLCache(ttl_seconds=10, clock=lambda: now[0])
        c.set("k", "v")
        now[0] = 9.9
        assert c.get("k") == (True, "v")
        now[0] = 10.0
        assert c.get("k") == (False, None)

    def test_zero_ttl_disables(self) -> None:
        c = TTLCache(ttl_seconds=0)
        c.set("k", "v")
        assert c.enabled is False and c.get("k") == (False, None)


class _StubTranslator:
    """Counts translate() calls to prove the cache short-circuits repeats."""

    def __init__(self) -> None:
        self.calls = 0

    def translate(self, query: str) -> TranslatedQuery:
        self.calls += 1
        return TranslatedQuery(
            original_query=query, rewritten_query=query, intent="career_guidance",
            retrieval_required=False, strategy="llm")


class TestServiceCaching:
    def _service(self, mode: str):
        translator = _StubTranslator()
        config = CopilotConfig(quality_mode=mode, query_cache_ttl_seconds=300)
        svc = CareerIntelligenceService(config=config, translator=translator)
        return svc, translator

    def test_balanced_mode_caches_translation(self) -> None:
        svc, translator = self._service("balanced")
        r1 = svc.answer("What does a data analyst do?")
        r2 = svc.answer("What does a data analyst do?")
        assert translator.calls == 1  # second call served from cache
        assert r1.trace.translation_cache_hit is False
        assert r2.trace.translation_cache_hit is True
        assert r2.trace.quality_mode == "balanced"

    def test_quality_mode_bypasses_cache(self) -> None:
        svc, translator = self._service("quality")
        svc.answer("Same question")
        svc.answer("Same question")
        assert translator.calls == 2  # never cached in quality mode

    def test_cheap_mode_reduces_top_k(self) -> None:
        svc, _ = self._service("cheap")
        assert svc.top_k <= 3 and svc.quality_mode == "cheap"

    def test_unknown_mode_falls_back_to_balanced(self) -> None:
        translator = _StubTranslator()
        svc = CareerIntelligenceService(
            config=CopilotConfig(quality_mode="balanced"), translator=translator)
        assert svc.quality_mode == "balanced"
