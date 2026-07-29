"""Pricing and usage accounting for OpenRouter requests.

Cost handling follows a clear precedence:

1. **Reported** — the cost OpenRouter returns in a request's usage data.
2. **Calculated** — an estimate derived from live model-metadata pricing when
   no reported cost is available.
3. **Unavailable** — neither a reported cost nor pricing metadata is available.

Prices are **never hard-coded**: they are read from the OpenRouter ``/models``
endpoint and cached for the running session. All figures are in US dollars, and
calculated figures are estimates — **not** final billed amounts. Calculations
use :class:`decimal.Decimal` for precision.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

import httpx

from src import constants
from src.models import ModelPricing, UsageRecord

__all__ = [
    "REPORTED",
    "CALCULATED",
    "UNAVAILABLE",
    "COST_ESTIMATE_DISCLAIMER",
    "SessionUsageTotals",
    "PricingService",
    "format_usd",
]

# Cost-source labels (kept in sync with constants.COST_SOURCES).
REPORTED = "reported"
CALCULATED = "calculated"
UNAVAILABLE = "unavailable"

COST_ESTIMATE_DISCLAIMER = constants.COST_ESTIMATE_DISCLAIMER

ModelsFetcher = Callable[[], list[dict]]


def format_usd(value: float | None) -> str:
    """Format a USD cost for display, or a dash when unavailable."""
    if value is None:
        return "—"
    return f"${value:,.6f}"


@dataclass(frozen=True)
class SessionUsageTotals:
    """Cumulative usage across a session."""

    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    reported_cost_usd: float
    calculated_cost_usd: float

    @property
    def best_effort_cost_usd(self) -> float:
        """Reported cost where available, otherwise the calculated estimate."""
        return self.reported_cost_usd + self.calculated_cost_usd


def _to_decimal(raw: object) -> Decimal | None:
    """Convert an OpenRouter price string/number to a Decimal, or None."""
    if raw is None:
        return None
    try:
        value = Decimal(str(raw))
    except (ArithmeticError, ValueError, TypeError):
        return None
    if value < 0:
        return None
    return value


class PricingService:
    """Fetches and caches model pricing; resolves and accumulates costs."""

    def __init__(
        self,
        models_fetcher: ModelsFetcher | None = None,
        *,
        models_url: str = constants.OPENROUTER_BASE_URL
        + constants.OPENROUTER_MODELS_PATH,
        connect_timeout: float = constants.CONNECT_TIMEOUT_SECONDS,
        read_timeout: float = constants.READ_TIMEOUT_SECONDS,
    ) -> None:
        self._fetcher = models_fetcher or self._default_fetcher
        self._models_url = models_url
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        # Raw metadata cached for the session (None until first load).
        self._raw_by_id: dict[str, dict] | None = None
        self._records: list[UsageRecord] = []

    # -- metadata fetch + cache ----------------------------------------------

    def _default_fetcher(self) -> list[dict]:
        """Fetch the ``/models`` list from OpenRouter (public, no auth needed)."""
        timeout = httpx.Timeout(
            connect=self._connect_timeout,
            read=self._read_timeout,
            write=self._read_timeout,
            pool=self._connect_timeout,
        )
        response = httpx.get(self._models_url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, list) else []

    def _ensure_loaded(self) -> dict[str, dict]:
        """Load and cache metadata once per session."""
        if self._raw_by_id is None:
            entries = self._fetcher()
            self._raw_by_id = {
                entry["id"]: entry
                for entry in entries
                if isinstance(entry, dict) and "id" in entry
            }
        return self._raw_by_id

    def clear_cache(self) -> None:
        """Forget cached metadata (forces a refetch on next access)."""
        self._raw_by_id = None

    # -- metadata accessors ---------------------------------------------------

    def get_model_pricing(self, model_id: str) -> ModelPricing | None:
        """Return validated pricing for a model, or None if unavailable."""
        entry = self._ensure_loaded().get(model_id)
        if entry is None:
            return None
        pricing = entry.get("pricing")
        if not isinstance(pricing, dict):
            return None
        prompt = _to_decimal(pricing.get("prompt"))
        completion = _to_decimal(pricing.get("completion"))
        if prompt is None or completion is None:
            return None
        request_fee = _to_decimal(pricing.get("request")) or Decimal("0")
        return ModelPricing(
            model_id=model_id,
            prompt_usd_per_token=float(prompt),
            completion_usd_per_token=float(completion),
            request_usd=float(request_fee),
        )

    def supported_parameters(self, model_id: str) -> tuple[str, ...]:
        """Return the model's supported_parameters from metadata."""
        entry = self._ensure_loaded().get(model_id)
        if entry is None:
            return ()
        params = entry.get("supported_parameters")
        if isinstance(params, list):
            return tuple(str(p) for p in params)
        return ()

    def supports_response_format(self, model_id: str) -> bool:
        """Whether the model supports structured output (response_format)."""
        return "response_format" in self.supported_parameters(model_id)

    # -- cost resolution ------------------------------------------------------

    def calculate_cost_usd(
        self, pricing: ModelPricing, prompt_tokens: int, completion_tokens: int
    ) -> Decimal:
        """Exact estimated cost as a Decimal (unrounded), in USD."""
        prompt_price = Decimal(str(pricing.prompt_usd_per_token))
        completion_price = Decimal(str(pricing.completion_usd_per_token))
        request_fee = Decimal(str(pricing.request_usd))
        return (
            prompt_price * Decimal(prompt_tokens)
            + completion_price * Decimal(completion_tokens)
            + request_fee
        )

    def _rounded(self, value: Decimal) -> float:
        quantum = Decimal(1).scaleb(-constants.PRICING_DECIMAL_PLACES)
        return float(value.quantize(quantum))

    def resolve_cost(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        reported_cost: float | None,
    ) -> tuple[float | None, str]:
        """Return ``(cost_usd, source)`` following the reported→calculated→none rule."""
        if reported_cost is not None:
            return float(reported_cost), REPORTED
        pricing = self.get_model_pricing(model_id)
        if pricing is not None:
            estimate = self.calculate_cost_usd(pricing, prompt_tokens, completion_tokens)
            return self._rounded(estimate), CALCULATED
        return None, UNAVAILABLE

    def build_usage_record(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        reported_cost: float | None,
        request_duration_seconds: float,
    ) -> UsageRecord:
        """Assemble a validated :class:`UsageRecord` with resolved cost."""
        pricing = self.get_model_pricing(model)
        calculated = (
            self._rounded(
                self.calculate_cost_usd(pricing, prompt_tokens, completion_tokens)
            )
            if pricing is not None
            else 0.0
        )

        if reported_cost is not None:
            source = REPORTED
        elif pricing is not None:
            source = CALCULATED
        else:
            source = UNAVAILABLE

        return UsageRecord(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            reported_cost=float(reported_cost) if reported_cost is not None else None,
            calculated_cost=calculated,
            cost_source=source,
            currency=constants.DEFAULT_CURRENCY,
            request_duration_seconds=request_duration_seconds,
        )

    # -- session accumulation -------------------------------------------------

    def record_usage(self, record: UsageRecord) -> None:
        """Add a usage record to the running session total."""
        self._records.append(record)

    @property
    def records(self) -> Sequence[UsageRecord]:
        return tuple(self._records)

    def session_totals(self) -> SessionUsageTotals:
        """Aggregate all recorded usage for the session."""
        prompt = sum(r.prompt_tokens for r in self._records)
        completion = sum(r.completion_tokens for r in self._records)
        total = sum(r.total_tokens for r in self._records)
        reported = sum(
            r.reported_cost for r in self._records if r.reported_cost is not None
        )
        # Count calculated estimates only where there was no reported figure, so
        # the two totals do not double-count the same request.
        calculated = sum(
            r.calculated_cost
            for r in self._records
            if r.cost_source == CALCULATED
        )
        return SessionUsageTotals(
            requests=len(self._records),
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            reported_cost_usd=float(reported),
            calculated_cost_usd=float(calculated),
        )
