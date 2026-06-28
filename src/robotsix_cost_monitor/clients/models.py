"""Pydantic v2 response models for Langfuse public API shapes.

Two distinct response shapes are consumed by the cost-monitor:

1. **Metrics API rows** (``/api/public/metrics``) — :class:`LangfuseMetricsRow`
2. **Trace objects** (``/api/public/traces``) — :class:`LangfuseTrace`

These models parse once at the API boundary, validate field types, and
provide mypy-visible attribute access — replacing the previous
``dict[str, Any]`` pattern that masked missing-key bugs as silent
``None`` → ``0.0`` propagation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LangfuseMetricsRow(BaseModel):
    """A single row from the Langfuse ``/api/public/metrics`` response.

    Field names are Python snake_case; Pydantic aliases map Langfuse's
    camelCase / mixed-case JSON keys (e.g. ``providedModelName`` →
    ``provided_model_name``, ``sum_totalCost`` → ``sum_total_cost``).
    ``populate_by_name=True`` allows construction from either form.
    """

    provided_model_name: str | None = Field(default=None, alias="providedModelName")
    trace_name: str | None = Field(default=None, alias="traceName")
    time_dimension: str | None = None
    sum_total_cost: float | None = Field(default=None, alias="sum_totalCost")
    sum_input_tokens: float | None = Field(default=None, alias="sum_inputTokens")
    sum_output_tokens: float | None = Field(default=None, alias="sum_outputTokens")
    sum_total_tokens: float | None = Field(default=None, alias="sum_totalTokens")
    count_count: float | None = None

    model_config = {"populate_by_name": True}


class LangfuseTrace(BaseModel):
    """A single trace from the Langfuse ``/api/public/traces`` response.

    Handles both ``sessionId`` (canonical Langfuse API key) and
    ``session_id`` (observed in some responses) via ``populate_by_name``.
    """

    id: str | None = None
    name: str | None = None
    session_id: str | None = Field(default=None, alias="sessionId")
    timestamp: str | None = None
    total_cost: float | None = Field(default=None, alias="totalCost")
    calculated_total_cost: float | None = Field(
        default=None, alias="calculatedTotalCost"
    )
    cost: float | None = None

    model_config = {"populate_by_name": True}
