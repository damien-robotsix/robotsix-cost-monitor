"""Unit tests for Pydantic v2 response models (LangfuseMetricsRow, LangfuseTrace).

Pure model-validation tests — no network, no mocking needed.
"""

from __future__ import annotations

from robotsix_cost_monitor.clients.models import (
    LangfuseMetricsRow,
    LangfuseTrace,
)

# ---------------------------------------------------------------------------
# LangfuseMetricsRow
# ---------------------------------------------------------------------------


class TestLangfuseMetricsRow:
    """Tests for the LangfuseMetricsRow model (8 fields)."""

    # -- alias resolution ---------------------------------------------------

    def test_construct_from_camelcase_keys(self) -> None:
        """All alias-bearing fields are resolved from camelCase JSON keys."""
        row = LangfuseMetricsRow.model_validate(
            {
                "providedModelName": "claude-sonnet-4-20250514",
                "traceName": "implement",
                "time_dimension": "2026-01-01T12:00:00Z",
                "sum_totalCost": 1.2345,
                "sum_inputTokens": 500,
                "sum_outputTokens": 200,
                "sum_totalTokens": 700,
                "count_count": 3,
            }
        )
        assert row.provided_model_name == "claude-sonnet-4-20250514"
        assert row.trace_name == "implement"
        assert row.time_dimension == "2026-01-01T12:00:00Z"
        assert row.sum_total_cost == 1.2345
        assert row.sum_input_tokens == 500
        assert row.sum_output_tokens == 200
        assert row.sum_total_tokens == 700
        assert row.count_count == 3

    def test_construct_from_snakecase_keys(self) -> None:
        """populate_by_name allows construction from snake_case keys directly."""
        row = LangfuseMetricsRow.model_validate(
            {
                "provided_model_name": "gpt-4o",
                "trace_name": "review",
                "time_dimension": "2026-06-01T00:00:00Z",
                "sum_total_cost": 0.05,
                "sum_input_tokens": 10,
                "sum_output_tokens": 5,
                "sum_total_tokens": 15,
                "count_count": 1,
            }
        )
        assert row.provided_model_name == "gpt-4o"
        assert row.trace_name == "review"
        assert row.sum_total_cost == 0.05

    def test_construct_from_mixed_keys(self) -> None:
        """CamelCase and snake_case keys coexist; last writer wins per name."""
        row = LangfuseMetricsRow.model_validate(
            {
                "providedModelName": "opus",
                "trace_name": "audit",
                "time_dimension": "2026-01-15T08:00:00Z",
                "sum_totalCost": 3.0,
                "sum_input_tokens": 1000,  # snake_case
                "sum_outputTokens": 500,  # camelCase
                "sum_totalTokens": 1500,
                "count_count": 2,
            }
        )
        assert row.provided_model_name == "opus"
        assert row.trace_name == "audit"
        assert row.sum_total_cost == 3.0
        assert row.sum_input_tokens == 1000
        assert row.sum_output_tokens == 500
        assert row.sum_total_tokens == 1500
        assert row.count_count == 2

    # -- missing optional fields --------------------------------------------

    def test_missing_optional_fields_are_none(self) -> None:
        """Every field is Optional; missing keys produce None."""
        row = LangfuseMetricsRow.model_validate({})
        assert row.provided_model_name is None
        assert row.trace_name is None
        assert row.time_dimension is None
        assert row.sum_total_cost is None
        assert row.sum_input_tokens is None
        assert row.sum_output_tokens is None
        assert row.sum_total_tokens is None
        assert row.count_count is None

    def test_partial_fields_some_none(self) -> None:
        """Only supplied fields are populated; others stay None."""
        row = LangfuseMetricsRow.model_validate(
            {"providedModelName": "haiku", "sum_totalCost": 0.01}
        )
        assert row.provided_model_name == "haiku"
        assert row.sum_total_cost == 0.01
        assert row.trace_name is None
        assert row.sum_input_tokens is None

    # -- extra fields -------------------------------------------------------

    def test_extra_fields_are_ignored(self) -> None:
        """Pydantic's default extra='ignore' discards unknown keys silently."""
        row = LangfuseMetricsRow.model_validate(
            {
                "providedModelName": "opus",
                "sum_totalCost": 10.0,
                "unknown_field": "should be ignored",
                "another_extra": 42,
            }
        )
        assert row.provided_model_name == "opus"
        assert row.sum_total_cost == 10.0
        # No attribute error for unknown keys

    # -- edge cases ---------------------------------------------------------

    def test_empty_strings_preserved(self) -> None:
        """String fields are Optional[str] — empty strings are kept as-is."""
        row = LangfuseMetricsRow.model_validate(
            {"providedModelName": "", "traceName": ""}
        )
        assert row.provided_model_name == ""
        assert row.trace_name == ""

    def test_zero_costs_and_counts(self) -> None:
        """Zero-valued numeric fields are preserved as 0.0, not coerced to None."""
        row = LangfuseMetricsRow.model_validate(
            {
                "sum_totalCost": 0.0,
                "sum_inputTokens": 0,
                "sum_outputTokens": 0,
                "sum_totalTokens": 0,
                "count_count": 0,
            }
        )
        assert row.sum_total_cost == 0.0
        assert row.sum_input_tokens == 0.0  # int 0 coerced to float
        assert row.sum_output_tokens == 0.0
        assert row.sum_total_tokens == 0.0
        assert row.count_count == 0.0

    def test_explicit_none_preserved(self) -> None:
        """Explicit null values remain None."""
        row = LangfuseMetricsRow.model_validate(
            {
                "providedModelName": None,
                "sum_totalCost": None,
            }
        )
        assert row.provided_model_name is None
        assert row.sum_total_cost is None


# ---------------------------------------------------------------------------
# LangfuseTrace
# ---------------------------------------------------------------------------


class TestLangfuseTrace:
    """Tests for the LangfuseTrace model (7 fields)."""

    # -- alias resolution ---------------------------------------------------

    def test_construct_from_camelcase_keys(self) -> None:
        """Aliased fields resolve from camelCase JSON keys."""
        trace = LangfuseTrace.model_validate(
            {
                "id": "tr-abc123",
                "name": "implement",
                "sessionId": "sess-xyz",
                "timestamp": "2026-01-01T12:00:00Z",
                "totalCost": 2.5,
                "calculatedTotalCost": 2.5,
                "cost": 2.5,
            }
        )
        assert trace.id == "tr-abc123"
        assert trace.name == "implement"
        assert trace.session_id == "sess-xyz"
        assert trace.timestamp == "2026-01-01T12:00:00Z"
        assert trace.total_cost == 2.5
        assert trace.calculated_total_cost == 2.5
        assert trace.cost == 2.5

    def test_construct_from_snakecase_keys(self) -> None:
        """populate_by_name allows snake_case keys for aliased fields."""
        trace = LangfuseTrace.model_validate(
            {
                "id": "tr-def456",
                "name": "review",
                "session_id": "sess-456",
                "timestamp": "2026-06-01T00:00:00Z",
                "total_cost": 0.05,
                "calculated_total_cost": 0.05,
                "cost": 0.05,
            }
        )
        assert trace.id == "tr-def456"
        assert trace.name == "review"
        assert trace.session_id == "sess-456"
        assert trace.total_cost == 0.05
        assert trace.calculated_total_cost == 0.05

    def test_construct_from_mixed_keys(self) -> None:
        """CamelCase and snake_case coexist for aliased fields."""
        trace = LangfuseTrace.model_validate(
            {
                "id": "tr-mix",
                "name": "audit",
                "sessionId": "sess-camel",
                "total_cost": 1.0,
                "calculatedTotalCost": 2.0,
                "cost": 3.0,
            }
        )
        assert trace.session_id == "sess-camel"
        assert trace.total_cost == 1.0
        assert trace.calculated_total_cost == 2.0
        assert trace.cost == 3.0

    # -- missing optional fields --------------------------------------------

    def test_missing_optional_fields_are_none(self) -> None:
        """Every field is Optional; missing keys produce None."""
        trace = LangfuseTrace.model_validate({})
        assert trace.id is None
        assert trace.name is None
        assert trace.session_id is None
        assert trace.timestamp is None
        assert trace.total_cost is None
        assert trace.calculated_total_cost is None
        assert trace.cost is None

    def test_partial_fields_some_none(self) -> None:
        """Only supplied fields are populated; others stay None."""
        trace = LangfuseTrace.model_validate({"id": "tr-1", "name": "test"})
        assert trace.id == "tr-1"
        assert trace.name == "test"
        assert trace.session_id is None
        assert trace.total_cost is None
        assert trace.calculated_total_cost is None

    # -- extra fields -------------------------------------------------------

    def test_extra_fields_are_ignored(self) -> None:
        """Pydantic's default extra='ignore' discards unknown keys silently."""
        trace = LangfuseTrace.model_validate(
            {
                "id": "tr-extra",
                "totalCost": 5.0,
                "metadata": {"key": "value"},
                "observations": [1, 2, 3],
            }
        )
        assert trace.id == "tr-extra"
        assert trace.total_cost == 5.0

    # -- edge cases ---------------------------------------------------------

    def test_empty_strings_preserved(self) -> None:
        """String fields are Optional[str] — empty strings are kept as-is."""
        trace = LangfuseTrace.model_validate({"id": "", "name": "", "sessionId": ""})
        assert trace.id == ""
        assert trace.name == ""
        assert trace.session_id == ""

    def test_zero_costs(self) -> None:
        """Zero-valued cost fields are preserved as 0.0, not coerced to None."""
        trace = LangfuseTrace.model_validate(
            {
                "totalCost": 0.0,
                "calculatedTotalCost": 0,
                "cost": 0,
            }
        )
        assert trace.total_cost == 0.0
        assert trace.calculated_total_cost == 0.0  # int 0 coerced to float
        assert trace.cost == 0.0

    def test_explicit_none_preserved(self) -> None:
        """Explicit null values remain None."""
        trace = LangfuseTrace.model_validate(
            {
                "id": "tr-null",
                "totalCost": None,
                "calculatedTotalCost": None,
            }
        )
        assert trace.id == "tr-null"
        assert trace.total_cost is None
        assert trace.calculated_total_cost is None

    def test_session_id_resolution_via_alias(self) -> None:
        """SessionId alias is the canonical Langfuse key; resolves correctly."""
        trace = LangfuseTrace.model_validate({"sessionId": "sess-alias-only"})
        assert trace.session_id == "sess-alias-only"

    def test_session_id_resolution_via_field_name(self) -> None:
        """session_id (snake_case) also works via populate_by_name."""
        trace = LangfuseTrace.model_validate({"session_id": "sess-field-name"})
        assert trace.session_id == "sess-field-name"
