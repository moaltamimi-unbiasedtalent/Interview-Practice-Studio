"""Tests for the pricing service.

The model-metadata fetch is always injected as a fake callable, so no real
OpenRouter request is made and no API key is used. Costs are checked for the
reported / calculated / unavailable distinction and for Decimal precision.
"""

from decimal import Decimal

import pytest

from src.models import UsageRecord
from src.pricing_service import (
    CALCULATED,
    REPORTED,
    UNAVAILABLE,
    PricingService,
    SessionUsageTotals,
    format_usd,
)

MINI = "openai/gpt-5-mini"
NANO = "openai/gpt-5-nano"
NO_PRICE = "free/no-price"


def _models() -> list[dict]:
    return [
        {
            "id": MINI,
            "pricing": {
                "prompt": "0.0000006",
                "completion": "0.0000018",
                "request": "0",
            },
            "supported_parameters": ["temperature", "max_tokens", "response_format"],
        },
        {
            "id": NANO,
            "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
            "supported_parameters": ["temperature", "max_tokens"],
        },
        {"id": NO_PRICE, "supported_parameters": ["temperature"]},
    ]


def _service() -> PricingService:
    return PricingService(models_fetcher=_models)


# --- Metadata & supported parameters ----------------------------------------


class TestMetadata:
    def test_pricing_read_from_metadata(self) -> None:
        pricing = _service().get_model_pricing(MINI)
        assert pricing is not None
        assert pricing.prompt_usd_per_token == 0.0000006
        assert pricing.completion_usd_per_token == 0.0000018
        assert pricing.currency == "USD"

    def test_missing_price_returns_none(self) -> None:
        assert _service().get_model_pricing(NO_PRICE) is None

    def test_unknown_model_returns_none(self) -> None:
        assert _service().get_model_pricing("no/such-model") is None

    def test_supported_parameters_read_from_metadata(self) -> None:
        service = _service()
        assert "response_format" in service.supported_parameters(MINI)
        assert service.supports_response_format(MINI) is True
        assert service.supports_response_format(NANO) is False

    def test_context_and_completion_limits_read_from_metadata(self) -> None:
        pricing = PricingService(
            models_fetcher=lambda: [
                {
                    "id": MINI,
                    "pricing": {"prompt": "0.0000006", "completion": "0.0000018"},
                    "context_length": 400_000,
                    "top_provider": {"max_completion_tokens": 128_000},
                }
            ]
        )
        assert pricing.context_length(MINI) == 400_000
        assert pricing.max_completion_tokens(MINI) == 128_000

    def test_limits_absent_or_invalid_return_none(self) -> None:
        pricing = PricingService(
            models_fetcher=lambda: [
                {
                    "id": MINI,
                    "pricing": {"prompt": "0.0000006", "completion": "0.0000018"},
                    # no context_length; top_provider present but no completion cap
                    "top_provider": {"is_moderated": True},
                },
                {
                    "id": NANO,
                    "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
                    "context_length": 0,  # non-positive -> treated as absent
                },
            ]
        )
        assert pricing.context_length(MINI) is None
        assert pricing.max_completion_tokens(MINI) is None
        assert pricing.context_length(NANO) is None
        assert pricing.context_length("no/such-model") is None
        assert pricing.max_completion_tokens("no/such-model") is None

    def test_metadata_cached_for_session(self) -> None:
        calls = {"n": 0}

        def counting_fetch() -> list[dict]:
            calls["n"] += 1
            return _models()

        service = PricingService(models_fetcher=counting_fetch)
        service.get_model_pricing(MINI)
        service.supported_parameters(NANO)
        service.get_model_pricing(NO_PRICE)
        assert calls["n"] == 1  # fetched once, then served from cache


# --- Cost resolution ---------------------------------------------------------


class TestCostResolution:
    def test_reported_cost_is_preferred(self) -> None:
        cost, source = _service().resolve_cost(MINI, 1000, 500, reported_cost=0.0009)
        assert source == REPORTED
        assert cost == 0.0009

    def test_fallback_calculation_when_no_reported_cost(self) -> None:
        cost, source = _service().resolve_cost(MINI, 1000, 500, reported_cost=None)
        assert source == CALCULATED
        # 0.0000006*1000 + 0.0000018*500 = 0.0015
        assert cost == pytest.approx(0.0015)

    def test_unavailable_when_no_reported_and_no_pricing(self) -> None:
        cost, source = _service().resolve_cost(NO_PRICE, 1000, 500, reported_cost=None)
        assert source == UNAVAILABLE
        assert cost is None

    def test_decimal_precision_is_exact(self) -> None:
        service = _service()
        pricing = service.get_model_pricing(MINI)
        assert pricing is not None
        exact = service.calculate_cost_usd(pricing, 1000, 500)
        expected = Decimal("0.0000006") * 1000 + Decimal("0.0000018") * 500
        assert isinstance(exact, Decimal)
        assert exact == expected

    def test_decimal_precision_tiny_counts(self) -> None:
        service = _service()
        pricing = service.get_model_pricing(NANO)
        assert pricing is not None
        exact = service.calculate_cost_usd(pricing, 3, 7)
        expected = Decimal("0.0000001") * 3 + Decimal("0.0000004") * 7
        assert exact == expected


# --- Usage records -----------------------------------------------------------


class TestUsageRecords:
    def test_record_uses_reported_cost(self) -> None:
        record = _service().build_usage_record(
            model=MINI,
            prompt_tokens=1000,
            completion_tokens=500,
            reported_cost=0.0009,
            request_duration_seconds=1.2,
        )
        assert isinstance(record, UsageRecord)
        assert record.cost_source == REPORTED
        assert record.reported_cost == 0.0009
        assert record.currency == "USD"
        assert record.total_tokens == 1500

    def test_record_uses_calculated_estimate(self) -> None:
        record = _service().build_usage_record(
            model=MINI,
            prompt_tokens=1000,
            completion_tokens=500,
            reported_cost=None,
            request_duration_seconds=1.2,
        )
        assert record.cost_source == CALCULATED
        assert record.reported_cost is None
        assert record.calculated_cost == pytest.approx(0.0015)

    def test_record_unavailable_cost(self) -> None:
        # An approved model whose pricing is absent from the fetched metadata.
        record = _service().build_usage_record(
            model="openai/gpt-5",
            prompt_tokens=10,
            completion_tokens=5,
            reported_cost=None,
            request_duration_seconds=0.3,
        )
        assert record.cost_source == UNAVAILABLE
        assert record.reported_cost is None
        assert record.calculated_cost == 0.0


# --- Session totals ----------------------------------------------------------


class TestSessionTotals:
    def test_empty_session(self) -> None:
        totals = _service().session_totals()
        assert totals == SessionUsageTotals(0, 0, 0, 0, 0.0, 0.0)

    def test_cumulative_usage(self) -> None:
        service = _service()
        service.record_usage(
            service.build_usage_record(
                model=MINI,
                prompt_tokens=1000,
                completion_tokens=500,
                reported_cost=None,
                request_duration_seconds=1.0,
            )
        )
        service.record_usage(
            service.build_usage_record(
                model=MINI,
                prompt_tokens=10,
                completion_tokens=5,
                reported_cost=0.0005,
                request_duration_seconds=0.5,
            )
        )
        totals = service.session_totals()
        assert totals.requests == 2
        assert totals.prompt_tokens == 1010
        assert totals.completion_tokens == 505
        assert totals.total_tokens == 1515
        assert totals.reported_cost_usd == pytest.approx(0.0005)
        assert totals.calculated_cost_usd == pytest.approx(0.0015)
        # Reported and calculated are not double-counted for the same request.
        assert totals.best_effort_cost_usd == pytest.approx(0.0020)


# --- Formatting --------------------------------------------------------------


class TestFormatting:
    def test_format_usd(self) -> None:
        assert format_usd(0.0015).startswith("$")
        assert format_usd(None) == "—"
