from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Mapping

from backend.services.db.connector import (
    DatabaseConfigurationError,
    close_connection,
    open_write_connection,
    quote_identifier,
)
from backend.services.db.scanner import (
    _environment_int,
    _is_sampleable,
    _postgres_table_names,
    _sqlite_table_names,
)
from backend.services.masking import mask_value
from backend.services.persistence.mongo import audit_logs


def _manage_sqlite(
    connection: Any,
    identifier: str,
    action: str,
    new_value: str | None,
    max_tables: int,
) -> dict[str, Any]:
    impacted_locations = 0
    impacted_rows = 0

    tables = _sqlite_table_names(connection, max_tables)

    # DELETE is a logical deletion in this system:
    # replace the PII with the deterministic mask instead of deleting the row.
    effective_action = "MASK" if action == "DELETE" else action

    if effective_action == "MASK":
        replacement = mask_value(identifier)
    else:
        replacement = new_value if new_value is not None else "[REDACTED]"

    for table_name in tables:
        quoted_table = quote_identifier(table_name)
        columns = connection.execute(
            f"PRAGMA table_info({quoted_table})"
        ).fetchall()

        table_impacted = False

        for column_info in columns:
            column_name = str(column_info[1])
            column_type = str(column_info[2] or "unknown")
            quoted_column = quote_identifier(column_name)

            if not _is_sampleable(column_type):
                continue

            if effective_action in ("UPDATE", "MASK"):
                query = (
                    f"UPDATE {quoted_table} "
                    f"SET {quoted_column} = REPLACE({quoted_column}, ?, ?) "
                    f"WHERE {quoted_column} LIKE ?"
                )

                try:
                    connection.execute("SAVEPOINT col_remediate")

                    cursor = connection.execute(
                        query,
                        (
                            identifier,
                            replacement,
                            f"%{identifier}%",
                        ),
                    )

                    if cursor.rowcount > 0:
                        impacted_rows += cursor.rowcount
                        table_impacted = True

                    connection.execute("RELEASE col_remediate")

                except Exception:
                    connection.execute("ROLLBACK TO col_remediate")
                    continue

        if table_impacted:
            impacted_locations += 1

    connection.commit()

    return {
        "impacted_locations": impacted_locations,
        "impacted_rows": impacted_rows,
    }


def _manage_postgres(
    connection: Any,
    identifier: str,
    action: str,
    new_value: str | None,
    max_tables: int,
) -> dict[str, Any]:
    impacted_locations = 0
    impacted_rows = 0

    tables = _postgres_table_names(connection, max_tables)

    # DELETE is a logical deletion in this system:
    # replace the PII with the deterministic mask instead of deleting the row.
    effective_action = "MASK" if action == "DELETE" else action

    if effective_action == "MASK":
        replacement = mask_value(identifier)
    else:
        replacement = new_value if new_value is not None else "[REDACTED]"

    for schema_name, raw_table_name in tables:
        quoted_schema = quote_identifier(schema_name)
        quoted_table_name = quote_identifier(raw_table_name)
        qualified_table = f"{quoted_schema}.{quoted_table_name}"

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name, data_type, udt_name "
                "FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (schema_name, raw_table_name),
            )
            columns = cursor.fetchall()

        table_impacted = False

        for column_info in columns:
            column_name = str(column_info[0])
            column_type = str(column_info[1] or column_info[2] or "unknown")
            quoted_column = quote_identifier(column_name)

            if not _is_sampleable(column_type):
                continue

            if effective_action in ("UPDATE", "MASK"):
                query = (
                    f"UPDATE {qualified_table} "
                    f"SET {quoted_column} = "
                    f"REPLACE({quoted_column}::text, %s, %s)::text "
                    f"WHERE {quoted_column}::text ILIKE %s"
                )

                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SAVEPOINT col_remediate")

                        cursor.execute(
                            query,
                            (
                                identifier,
                                replacement,
                                f"%{identifier}%",
                            ),
                        )

                        if cursor.rowcount > 0:
                            impacted_rows += cursor.rowcount
                            table_impacted = True

                        cursor.execute("RELEASE col_remediate")

                except Exception:
                    with connection.cursor() as cursor:
                        cursor.execute("ROLLBACK TO col_remediate")
                    continue

        if table_impacted:
            impacted_locations += 1

    connection.commit()

    return {
        "impacted_locations": impacted_locations,
        "impacted_rows": impacted_rows,
    }


def manage_database_data(
    config: Mapping[str, Any],
    identifier: str,
    action: str,
    new_value: str | None = None,
) -> dict[str, Any]:
    """
    Remediate database data containing identifier.

    UPDATE:
        Replace the identifier with new_value.

    MASK:
        Replace the identifier with the deterministic mask.

    DELETE:
        Logical deletion only. The row is NOT deleted.
        The identifier is replaced with the deterministic mask.

    This means DELETE and MASK intentionally perform the same underlying
    database mutation, while DELETE remains the user-facing request action.
    """

    max_tables = _environment_int(
        "DB_SCAN_MAX_TABLES",
        100,
        1,
        500,
    )

    connection = open_write_connection(config)

    try:
        if config.get("engine") == "sqlite":
            result = _manage_sqlite(
                connection,
                identifier,
                action,
                new_value,
                max_tables,
            )

        elif config.get("engine") == "postgres":
            result = _manage_postgres(
                connection,
                identifier,
                action,
                new_value,
                max_tables,
            )

        else:
            raise DatabaseConfigurationError(
                "Unsupported database engine."
            )

    finally:
        close_connection(connection)

    org_id = config.get(
        "organisation_id",
        os.environ.get("ORG_ID", "dpdp-org"),
    )

    # For DELETE, report the mask that was actually written.
    masked_value = (
        mask_value(identifier)
        if action in ("MASK", "DELETE")
        else None
    )

    audit_logs.insert_one(
        {
            "actor_type": "system",
            "actor_id": "db-action-engine",
            "entity_type": "data_subject_request",
            "org_id": org_id,
            "action": action,
            "identifier": identifier,
            "tables_affected": result["impacted_locations"],
            "rows_affected": result["impacted_rows"],
            "timestamp": datetime.now(),
            "status": "SUCCESS",
            "source_type": "database",
            "engine": config.get("engine"),
            "remediation": (
                "mask"
                if action == "DELETE"
                else action.lower()
            ),
        }
    )

    return {
        "action": action,
        "identifier": identifier,
        "status": "SUCCESS",
        "message": (
            f"Database {action.title()} processed for {identifier}."
        ),
        "impacted_locations": result["impacted_locations"],
        "impacted_rows": result["impacted_rows"],
        "new_value": (
            new_value
            if action == "UPDATE"
            else masked_value
        ),
    }