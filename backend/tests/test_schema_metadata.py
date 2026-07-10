from pathlib import Path

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db import models  # noqa: F401
from app.db.base import Base

INITIAL_MIGRATION_PATH = "alembic/versions/0001_initial_schema_created_relayguard_initial_schema.py"
REPLAY_STATUS_MIGRATION_PATH = "alembic/versions/0002_replay_statuses.py"
WEBHOOK_INTAKE_MIGRATION_PATH = "alembic/versions/0003_webhook_intake_support.py"
ROUTING_SCHEDULE_MIGRATION_PATH = "alembic/versions/0004_routing_schedule.py"
DELIVERY_EXECUTION_MIGRATION_PATH = "alembic/versions/0005_delivery_execution.py"

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
    assert _has_unique_constraint(
        "event_deliveries",
        {"event_id", "destination_id", "routing_rule_id"},
    )
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
    assert _has_partial_unique_index(
        table_name="retry_jobs",
        index_name="uq_retry_jobs_pending_delivery_run_at",
        columns={"delivery_id", "run_at"},
        where_fragment="status = 'pending'",
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


def test_replay_request_status_check_includes_terminal_statuses() -> None:
    table = Base.metadata.tables["replay_requests"]
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    replay_status_check = checks["ck_replay_requests_replay_request_status"]
    assert "'resolved'" in replay_status_check
    assert "'executed'" in replay_status_check


def test_webhook_receipt_status_check_includes_duplicate() -> None:
    table = Base.metadata.tables["webhook_receipts"]
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    receipt_status_check = checks["ck_webhook_receipts_webhook_receipt_status"]
    assert "'accepted'" in receipt_status_check
    assert "'duplicate'" in receipt_status_check
    assert "'rejected'" in receipt_status_check


def test_phase_2_request_metadata_columns_exist() -> None:
    receipt_columns = Base.metadata.tables["webhook_receipts"].columns
    event_columns = Base.metadata.tables["events"].columns

    assert "request_method" in receipt_columns
    assert "request_path" in receipt_columns
    assert "content_type" in receipt_columns
    assert "body_size_bytes" in receipt_columns
    assert "correlation_id" in receipt_columns
    assert "accepted_at" in event_columns
    event_type = event_columns["event_type"].type
    assert isinstance(event_type, String)
    assert event_type.length == 255


def test_initial_migration_keeps_original_replay_request_statuses() -> None:
    migration_text = _read_backend_file(INITIAL_MIGRATION_PATH)
    replay_constraint_text = _migration_constraint_block(
        migration_text,
        "ck_replay_requests_replay_request_status",
    )

    assert (
        "status IN ('pending', 'approved', 'running', 'completed', 'rejected', 'cancelled')"
        in replay_constraint_text
    )
    assert "'resolved'" not in replay_constraint_text
    assert "'executed'" not in replay_constraint_text


def test_second_migration_expands_and_restores_replay_request_statuses() -> None:
    migration_text = _read_backend_file(REPLAY_STATUS_MIGRATION_PATH)

    assert 'revision: str = "0002_replay_statuses"' in migration_text
    assert 'down_revision: str | None = "0001_initial_schema"' in migration_text
    assert "'resolved'" in migration_text
    assert "'executed'" in migration_text
    assert (
        "status IN ('pending', 'approved', 'running', 'completed', 'rejected', 'cancelled')"
        in migration_text
    )


def test_third_migration_adds_webhook_intake_support() -> None:
    migration_text = _read_backend_file(WEBHOOK_INTAKE_MIGRATION_PATH)

    assert 'revision: str = "0003_webhook_intake_support"' in migration_text
    assert 'down_revision: str | None = "0002_replay_statuses"' in migration_text
    assert "'duplicate'" in migration_text
    assert '"request_method"' in migration_text
    assert '"request_path"' in migration_text
    assert '"body_size_bytes"' in migration_text
    assert '"correlation_id"' in migration_text
    assert '"accepted_at"' in migration_text


def test_fourth_migration_adds_delivery_scheduling_idempotency() -> None:
    migration_text = _read_backend_file(ROUTING_SCHEDULE_MIGRATION_PATH)

    assert 'revision: str = "0004_routing_schedule"' in migration_text
    assert 'down_revision: str | None = "0003_webhook_intake_support"' in migration_text
    assert "uq_event_deliveries_event_destination_routing_rule" in migration_text
    assert '"event_id", "destination_id", "routing_rule_id"' in migration_text


def test_phase_4_delivery_execution_columns_exist() -> None:
    delivery_columns = Base.metadata.tables["event_deliveries"].columns
    attempt_columns = Base.metadata.tables["delivery_attempts"].columns
    retry_columns = Base.metadata.tables["retry_jobs"].columns
    dead_letter_columns = Base.metadata.tables["dead_letter_events"].columns

    assert "delivered_at" in delivery_columns
    assert "last_error_code" in delivery_columns
    assert "last_error_message" in delivery_columns
    assert "outcome" in attempt_columns
    assert "error_code" in attempt_columns
    assert "is_retryable" in attempt_columns
    assert "created_at" in attempt_columns
    assert "claimed_at" in retry_columns
    assert "completed_at" in retry_columns
    assert "updated_at" in retry_columns
    assert "reason_code" in dead_letter_columns
    assert "reason_message" in dead_letter_columns
    assert "resolved_at" in dead_letter_columns
    assert "created_at" in dead_letter_columns
    assert "updated_at" in dead_letter_columns


def test_phase_4_status_checks_include_execution_statuses() -> None:
    delivery_checks = _check_constraints("event_deliveries")
    attempt_checks = _check_constraints("delivery_attempts")
    retry_checks = _check_constraints("retry_jobs")

    delivery_status_check = delivery_checks["ck_event_deliveries_event_delivery_status"]
    assert "'delivered'" in delivery_status_check
    assert "'cancelled'" in delivery_status_check
    assert "'dead_lettered'" in delivery_status_check
    attempt_outcome_check = attempt_checks["ck_delivery_attempts_delivery_attempt_outcome"]
    assert "'succeeded'" in attempt_outcome_check
    assert "'failed'" in attempt_outcome_check
    assert "'timed_out'" in attempt_outcome_check
    retry_status_check = retry_checks["ck_retry_jobs_retry_job_status"]
    assert "'pending'" in retry_status_check
    assert "'claimed'" in retry_status_check
    assert "'completed'" in retry_status_check
    assert "'cancelled'" in retry_status_check


def test_fifth_migration_adds_delivery_execution_support() -> None:
    migration_text = _read_backend_file(DELIVERY_EXECUTION_MIGRATION_PATH)

    assert 'revision: str = "0005_delivery_execution"' in migration_text
    assert 'down_revision: str | None = "0004_routing_schedule"' in migration_text
    assert '"delivered_at"' in migration_text
    assert '"outcome"' in migration_text
    assert '"is_retryable"' in migration_text
    assert '"claimed_at"' in migration_text
    assert '"completed_at"' in migration_text
    assert '"reason_code"' in migration_text
    assert "uq_retry_jobs_pending_delivery_run_at" in migration_text


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


def _check_constraints(table_name: str) -> dict[str, str]:
    table = Base.metadata.tables[table_name]
    return {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _index_column_names(index: Index) -> set[str]:
    names: set[str] = set()
    for expression in index.expressions:
        name = getattr(expression, "name", None)
        if isinstance(name, str):
            names.add(name)
    return names


def _read_backend_file(path: str) -> str:
    return (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8")


def _migration_constraint_block(migration_text: str, constraint_name: str) -> str:
    constraint_index = migration_text.index(constraint_name)
    block_start = migration_text.rfind("sa.CheckConstraint(", 0, constraint_index)
    block_end = migration_text.index("),", constraint_index)
    return migration_text[block_start:block_end]
