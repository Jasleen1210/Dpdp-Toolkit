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
from backend.services.persistence.mongo import audit_logs


def _manage_sqlite(connection: Any, identifier: str, action: str, new_value: str | None, max_tables: int) -> dict[str, Any]:
    impacted_locations = 0
    impacted_rows = 0

    tables = _sqlite_table_names(connection, max_tables)
    
    replacement = new_value if new_value is not None else "[REDACTED]"

    for table_name in tables:
        quoted_table = quote_identifier(table_name)
        columns = connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()
        
        table_impacted = False

        for column_info in columns:
            column_name = str(column_info[1])
            column_type = str(column_info[2] or "unknown")
            quoted_column = quote_identifier(column_name)

            if _is_sampleable(column_type):
                if action == "UPDATE":
                    query = f"UPDATE {quoted_table} SET {quoted_column} = REPLACE({quoted_column}, ?, ?) WHERE {quoted_column} LIKE ?"
                    try:
                        connection.execute("SAVEPOINT col_remediate")
                        cursor = connection.execute(query, (identifier, replacement, f"%{identifier}%"))
                        if cursor.rowcount > 0:
                            impacted_rows += cursor.rowcount
                            table_impacted = True
                        connection.execute("RELEASE col_remediate")
                    except Exception:
                        connection.execute("ROLLBACK TO col_remediate")
                        continue
                elif action == "DELETE":
                    query = f"DELETE FROM {quoted_table} WHERE {quoted_column} LIKE ?"
                    try:
                        connection.execute("SAVEPOINT col_remediate")
                        cursor = connection.execute(query, (f"%{identifier}%",))
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


def _manage_postgres(connection: Any, identifier: str, action: str, new_value: str | None, max_tables: int) -> dict[str, Any]:
    impacted_locations = 0
    impacted_rows = 0

    tables = _postgres_table_names(connection, max_tables)
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

            if _is_sampleable(column_type):
                with connection.cursor() as cursor:
                    if action == "UPDATE":
                        query = f"UPDATE {qualified_table} SET {quoted_column} = REPLACE({quoted_column}::text, %s, %s)::{column_type} WHERE {quoted_column}::text ILIKE %s"
                        try:
                            cursor.execute("SAVEPOINT col_remediate")
                            cursor.execute(query, (identifier, replacement, f"%{identifier}%"))
                            if cursor.rowcount > 0:
                                impacted_rows += cursor.rowcount
                                table_impacted = True
                            cursor.execute("RELEASE col_remediate")
                        except Exception:
                            cursor.execute("ROLLBACK TO col_remediate")
                            continue
                            
                    elif action == "DELETE":
                        query = f"DELETE FROM {qualified_table} WHERE {quoted_column}::text ILIKE %s"
                        try:
                            cursor.execute("SAVEPOINT col_remediate")
                            cursor.execute(query, (f"%{identifier}%",))
                            if cursor.rowcount > 0:
                                impacted_rows += cursor.rowcount
                                table_impacted = True
                            cursor.execute("RELEASE col_remediate")
                        except Exception:
                            cursor.execute("ROLLBACK TO col_remediate")
                            continue
                            
        if table_impacted:
            impacted_locations += 1
            
    connection.commit()

    return {
        "impacted_locations": impacted_locations,
        "impacted_rows": impacted_rows,
    }


def manage_database_data(config: Mapping[str, Any], identifier: str, action: str, new_value: str | None = None) -> dict[str, Any]:
    """
    Search and replace/delete records containing `identifier` in the configured database.
    Supported actions:
      * "UPDATE" – replace with a custom `new_value`.
      * "REDACT" – replace with the sentinel "[REDACTED]".
      * "MASK" – replace with the sentinel "[MASKED]".
      * "DELETE" – delete the whole row.
    """
    max_tables = _environment_int("DB_SCAN_MAX_TABLES", 100, 1, 500)
    connection = open_write_connection(config)
    original_action = action

    try:
        # Map REDACT and MASK to UPDATE with appropriate sentinel values
        if action in ("REDACT", "MASK"):
            # Use the appropriate sentinel replacement and force UPDATE semantics
            new_value = "[REDACTED]" if action == "REDACT" else "[MASKED]"
            action = "UPDATE"
        if config.get("engine") == "sqlite":
            result = _manage_sqlite(connection, identifier, action, new_value, max_tables)
        elif config.get("engine") == "postgres":
            result = _manage_postgres(connection, identifier, action, new_value, max_tables)
        else:
            raise DatabaseConfigurationError("Unsupported database engine.")
    finally:
        # close_connection attempts a rollback which is safe if already committed
        close_connection(connection)

    # Log to audit logs similarly to cloud remediation
    org_id = config.get("organisation_id", os.environ.get("ORG_ID", "dpdp-org"))
    audit_logs.insert_one({
        "actor_type": "system",
        "actor_id": "db-action-engine",
        "entity_type": "data_subject_request",
        "org_id": org_id,
        "action": action,  # Action now reflects REDACT, MASK, UPDATE or DELETE
        "identifier": identifier,
        "tables_affected": result["impacted_locations"],
        "rows_affected": result["impacted_rows"],
        "timestamp": datetime.now(),
        "status": "SUCCESS",
        "source_type": "database",
        "engine": config.get("engine")
    })

    return {
        "action": action,
        "identifier": identifier,
        "status": "SUCCESS",
        "message": f"Database {action.title()} processed for {identifier}.",
        "impacted_locations": result["impacted_locations"],  # Number of tables
        "impacted_rows": result["impacted_rows"],
        "new_value": new_value if action == "UPDATE" else None,
    }
