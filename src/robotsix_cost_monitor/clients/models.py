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

    ``extra`` is ``"ignore"`` — and must stay that way.  Cached trace lists are
    the dominant memory consumer in this process: a 168 h window across the
    fleet is ~21 k traces, and Langfuse returns each one with its full ``input``
    / ``output`` / ``metadata`` payload.  Under ``extra="allow"`` Pydantic
    retained all of it in ``__pydantic_extra__`` — ~777 MB of raw JSON held
    live, which pegged the 2 GB container limit.  Nothing here reads those
    fields (aggregation only needs the seven declared ones), so they are
    dropped at the validation boundary rather than cached forever.
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

    model_config = {"populate_by_name": True, "extra": "ignore"}


class RegistryProject(BaseModel):
    """One Langfuse project discovered from the central-deploy registry.

    A project is a single LLM *function*, not a component: a component with
    two tracing subsystems declares two projects (e.g. ``robotsix-chat`` and
    ``robotsix-chat-cognee``).  :attr:`component_id` records which component
    owns it, so the dashboard can roll a component's projects up without any
    per-component code.
    """

    name: str
    slug: str
    component_id: str = Field(
        default="",
        description="Owning component (registry `component_id`); '' when unknown",
    )
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_base_url: str = "https://cloud.langfuse.com"
    openrouter_key: str | None = None
