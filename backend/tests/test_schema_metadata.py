from sqlalchemy import CheckConstraint, DateTime, Enum, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db import models  # noqa: F401
from app.db.base import Base

REQUIRED_TABLES = {
    "users",
    "roles",
    "user_roles",
    "auth_sessions",
    "integrations",
    "webhook_secrets",
    "event_schemas",
    "downstream_destinations",
    "routing_rules",
    "webhook_receipts",
    "events",
    "event_payloads",
    "event_state_transitions",
    "event_deliveries",
    "delivery_attempts",
    "retry_jobs",
    "dead_letter_events",
    "simulation_runs",
    "replay_requests",
    "ai_analyses",
    "ai_evaluation_runs",
    "audit_logs",
}

REQUIRED_OPERATIONAL_INDEXES = {
    "events": {
        "ix_events_integration_id_status_received_at",
        "ix_events_received_at",
    },
    "event_deliveries": {"ix_event_deliveries_status_next_attempt_at"},
    "retry_jobs": {"ix_retry_jobs_status_run_at"},
    "dead_letter_events": {
        "ix_dle_resolution_status_severity_dead_lettered_at",
    },
    "audit_logs": {
        "ix_audit_logs_resource_type_resource_id_created_at",
        "ix_audit_logs_actor_id_created_at",
    },
}


def test_required_tables_exist() -> None:
    assert set(Base.metadata.tables) == REQUIRED_TABLES


def test_every_table_has_uuid_primary_key() -> None:
    for table in Base.metadata.sorted_tables:
        primary_key_columns = list(table.primary_key.columns)
        assert len(primary_key_columns) == 1, table.name
        assert isinstance(primary_key_columns[0].type, UUID), table.name


def test_timestamp_columns_are_timezone_aware() -> None:
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if column.name.endswith("_at"):
                assert isinstance(column.type, DateTime), f"{table.name}.{column.name}"
                assert column.type.timezone is True, f"{table.name}.{column.name}"


def test_no_postgresql_enum_types_are_introduced() -> None:
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            assert not isinstance(column.type, Enum), f"{table.name}.{column.name}"


def test_jsonb_is_used_only_for_document_columns() -> None:
    allowed_jsonb_columns = {
        ("integrations", "configuration"),
        ("event_schemas", "schema_document"),
        ("downstream_destinations", "configuration"),
        ("routing_rules", "match_configuration"),
        ("webhook_receipts", "headers"),
        ("webhook_receipts", "query_params"),
        ("events", "event_metadata"),
        ("event_payloads", "payload"),
        ("event_state_transitions", "transition_metadata"),
        ("delivery_attempts", "request_headers"),
        ("delivery_attempts", "response_headers"),
        ("dead_letter_events", "context_document"),
        ("simulation_runs", "input_document"),
        ("simulation_runs", "result_document"),
        ("replay_requests", "request_document"),
        ("ai_analyses", "detail_document"),
        ("ai_evaluation_runs", "evaluation_document"),
        ("audit_logs", "audit_document"),
    }
    actual_jsonb_columns = {
        (table.name, column.name)
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, JSONB)
    }

    assert actual_jsonb_columns == allowed_jsonb_columns


def test_required_unique_constraints_exist() -> None:
    assert _has_unique_constraint("user_roles", {"user_id", "role_id"})
    assert _has_unique_constraint("event_payloads", {"event_id"})
    assert _has_unique_constraint("dead_letter_events", {"delivery_id"})
    assert _has_unique_constraint("events", {"integration_id", "deduplication_key"})
    assert _has_unique_constraint("delivery_attempts", {"delivery_id", "attempt_number"})
    assert _has_unique_constraint("auth_sessions", {"token_hash"})
    assert _has_unique_constraint("integrations", {"name"})
    assert _has_unique_constraint("integrations", {"slug"})


def test_required_partial_unique_indexes_exist() -> None:
    assert _has_partial_unique_index(
        table_name="events",
        index_name="uq_events_integration_id_source_event_id_not_null",
        columns={"integration_id", "source_event_id"},
        where_fragment="source_event_id IS NOT NULL",
    )
    assert _has_partial_unique_index(
        table_name="replay_requests",
        index_name="uq_replay_requests_active_dead_letter_event_id",
        columns={"dead_letter_event_id"},
        where_fragment="status IN ('pending', 'approved')",
    )


def test_required_operational_indexes_exist() -> None:
    for table_name, expected_index_names in REQUIRED_OPERATIONAL_INDEXES.items():
        actual_index_names = {index.name for index in Base.metadata.tables[table_name].indexes}
        assert expected_index_names <= actual_index_names


def test_event_state_transition_status_check_constraints_exist() -> None:
    table = Base.metadata.tables["event_state_transitions"]
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_event_state_transitions_event_state_transition_from_status" in checks
    assert (
        "from_status IS NULL"
        in checks["ck_event_state_transitions_event_state_transition_from_status"]
    )
    assert (
        "'accepted', 'processing', 'delivered', 'partially_failed', 'dead_lettered', 'cancelled'"
    ) in checks["ck_event_state_transitions_event_state_transition_from_status"]
    assert "ck_event_state_transitions_event_state_transition_to_status" in checks
    assert (
        "'accepted', 'processing', 'delivered', 'partially_failed', 'dead_lettered', 'cancelled'"
    ) in checks["ck_event_state_transitions_event_state_transition_to_status"]


def _has_unique_constraint(table_name: str, columns: set[str]) -> bool:
    table = Base.metadata.tables[table_name]
    return any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns} == columns
        for constraint in table.constraints
    )


def _has_partial_unique_index(
    *,
    table_name: str,
    index_name: str,
    columns: set[str],
    where_fragment: str,
) -> bool:
    table = Base.metadata.tables[table_name]
    for index in table.indexes:
        where = index.dialect_options["postgresql"].get("where")
        if (
            isinstance(index, Index)
            and index.name == index_name
            and index.unique is True
            and _index_column_names(index) == columns
            and where is not None
            and where_fragment in str(where)
        ):
            return True
    return False


def _index_column_names(index: Index) -> set[str]:
    names: set[str] = set()
    for expression in index.expressions:
        name = getattr(expression, "name", None)
        if isinstance(name, str):
            names.add(name)
    return names
