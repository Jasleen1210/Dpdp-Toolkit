from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

try:
    from backend.services.db.connector import (
        DatabaseConfigurationError,
        DatabaseConnectionError,
        connection_label,
        credential_is_configured,
        validate_source_config,
    )
    from backend.services.db.db import (
        database_audit_logs_collection,
        database_findings_collection,
        database_scan_runs_collection,
        database_sources_collection,
    )
    from backend.services.db.scanner import scan_database
    from backend.services.db.delete_update import manage_database_data
except ImportError:
    from services.db.connector import (
        DatabaseConfigurationError,
        DatabaseConnectionError,
        connection_label,
        credential_is_configured,
        validate_source_config,
    )
    from services.db.db import (
        database_audit_logs_collection,
        database_findings_collection,
        database_scan_runs_collection,
        database_sources_collection,
    )
    from services.db.scanner import scan_database
    from services.db.delete_update import manage_database_data


class DatabaseSourceNotFoundError(LookupError):
    """Raised when a source does not belong to the requested organisation."""


class DatabaseServiceError(RuntimeError):
    """Safe message suitable for returning to an API client."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_filter(organisation_id: str, source_id: str) -> dict[str, str]:
    return {"organisation_id": organisation_id, "id": source_id}


def _get_source_document(organisation_id: str, source_id: str) -> dict[str, Any]:
    source = database_sources_collection.find_one(
        _source_filter(organisation_id, source_id),
        {"_id": 0},
    )
    if not source:
        raise DatabaseSourceNotFoundError("Database source was not found.")
    return source


def _public_source(source: Mapping[str, Any]) -> dict[str, Any]:
    config = source.get("config", {})
    return {
        "id": source["id"],
        "organisation_id": source["organisation_id"],
        "display_name": source["display_name"],
        "engine": config.get("engine"),
        "connection_label": connection_label(config),
        "credential_configured": credential_is_configured(config),
        "created_at": source.get("created_at"),
        "updated_at": source.get("updated_at"),
        "last_scan_at": source.get("last_scan_at"),
        "last_scan_status": source.get("last_scan_status", "not_scanned"),
        "latest_summary": source.get("latest_summary", {}),
    }


def _public_run(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": run["id"],
        "source_id": run["source_id"],
        "organisation_id": run["organisation_id"],
        "status": run.get("status"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "summary": run.get("summary", {}),
        "error": run.get("error"),
    }


def _write_audit(
    *,
    organisation_id: str,
    source_id: str | None,
    user_id: str,
    action: str,
    status: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    database_audit_logs_collection.insert_one(
        {
            "id": str(uuid4()),
            "organisation_id": organisation_id,
            "source_id": source_id,
            "user_id": user_id,
            "action": action,
            "status": status,
            "details": dict(details or {}),
            "timestamp": _now(),
        }
    )


def create_database_source(
    *,
    organisation_id: str,
    user_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    config = validate_source_config(payload)
    display_name = str(payload.get("display_name") or "").strip()
    if len(display_name) < 2:
        raise DatabaseServiceError("display_name must contain at least two characters.")

    now = _now()
    source = {
        "id": str(uuid4()),
        "organisation_id": organisation_id,
        "display_name": display_name,
        "config": config,
        "created_by_user_id": user_id,
        "created_at": now,
        "updated_at": now,
        "last_scan_at": None,
        "last_attempt_at": None,
        "last_scan_status": "not_scanned",
        "latest_summary": {},
    }
    database_sources_collection.insert_one(source)

    _write_audit(
        organisation_id=organisation_id,
        source_id=source["id"],
        user_id=user_id,
        action="DATABASE_SOURCE_CREATED",
        status="SUCCESS",
        details={"engine": config["engine"]},
    )
    return _public_source(source)


def list_database_sources(organisation_id: str) -> list[dict[str, Any]]:
    sources = database_sources_collection.find(
        {"organisation_id": organisation_id},
        {"_id": 0},
    ).sort("created_at", -1)
    return [_public_source(source) for source in sources]

def create_configured_supabase_source(
    *,
    organisation_id: str,
    user_id: str,
) -> dict[str, Any]:
    """
    Register the Supabase PostgreSQL database configured in backend/.env.

    The password itself is never stored in MongoDB and never returned
    to the frontend. Only the name of the environment variable holding
    the password is stored.
    """
    host = os.getenv("DPDP_DB_SUPABASE_HOST", "").strip()
    port = os.getenv("DPDP_DB_SUPABASE_PORT", "5432").strip()
    database = os.getenv("DPDP_DB_SUPABASE_NAME", "").strip()
    username = os.getenv("DPDP_DB_SUPABASE_USER", "").strip()
    password = os.getenv("DPDP_DB_SUPABASE_PASSWORD", "").strip()

    if not host:
        raise DatabaseServiceError("DPDP_DB_SUPABASE_HOST is not configured.")

    if not database:
        raise DatabaseServiceError("DPDP_DB_SUPABASE_NAME is not configured.")

    if not username:
        raise DatabaseServiceError("DPDP_DB_SUPABASE_USER is not configured.")

    if not password:
        raise DatabaseServiceError("DPDP_DB_SUPABASE_PASSWORD is not configured.")

    try:
        port_number = int(port)
    except ValueError as exc:
        raise DatabaseServiceError(
            "DPDP_DB_SUPABASE_PORT must be a valid number."
        ) from exc

    payload = {
        "display_name": "Supabase PostgreSQL",
        "engine": "postgres",
        "postgres_host": host,
        "postgres_port": port_number,
        "postgres_database": database,
        "postgres_username": username,
        "password_env_var": "DPDP_DB_SUPABASE_PASSWORD",
        "sslmode": "require",
    }

    return create_database_source(
        organisation_id=organisation_id,
        user_id=user_id,
        payload=payload,
    )

def _build_summary(scan_result: Mapping[str, Any]) -> dict[str, Any]:
    findings = list(scan_result.get("findings", []))
    return {
        "finding_count": len(findings),
        "pii_instance_count": sum(int(item.get("match_count", 0)) for item in findings),
        "critical_finding_count": sum(1 for item in findings if item.get("risk") == "critical"),
        "high_finding_count": sum(1 for item in findings if item.get("risk") == "high"),
        "scanned_tables": int(scan_result.get("scanned_tables", 0)),
        "inspected_columns": int(scan_result.get("inspected_columns", 0)),
        "sampled_values": int(scan_result.get("sampled_values", 0)),
        "warning_count": len(scan_result.get("warnings", [])),
    }


def scan_database_source(
    *,
    organisation_id: str,
    source_id: str,
    user_id: str,
) -> dict[str, Any]:
    source = _get_source_document(organisation_id, source_id)
    now = _now()
    run_id = str(uuid4())
    run = {
        "id": run_id,
        "organisation_id": organisation_id,
        "source_id": source_id,
        "triggered_by_user_id": user_id,
        "status": "RUNNING",
        "started_at": now,
        "completed_at": None,
        "summary": {},
        "error": None,
    }
    database_scan_runs_collection.insert_one(run)
    database_sources_collection.update_one(
        _source_filter(organisation_id, source_id),
        {"$set": {"last_attempt_at": now, "last_scan_status": "running", "updated_at": now}},
    )

    try:
        scan_result = scan_database(source["config"])
        findings = list(scan_result.get("findings", []))
        summary = _build_summary(scan_result)
        completed_at = _now()

        # Keep only the latest successful discovery inventory for each source.
        database_findings_collection.delete_many(
            {"organisation_id": organisation_id, "source_id": source_id}
        )
        if findings:
            database_findings_collection.insert_many(
                [
                    {
                        "id": str(uuid4()),
                        "organisation_id": organisation_id,
                        "source_id": source_id,
                        "scan_run_id": run_id,
                        "created_at": completed_at,
                        **finding,
                    }
                    for finding in findings
                ]
            )

        database_scan_runs_collection.update_one(
            {"id": run_id},
            {
                "$set": {
                    "status": "COMPLETED",
                    "completed_at": completed_at,
                    "summary": summary,
                    "warnings": list(scan_result.get("warnings", [])),
                }
            },
        )
        database_sources_collection.update_one(
            _source_filter(organisation_id, source_id),
            {
                "$set": {
                    "last_scan_at": completed_at,
                    "last_attempt_at": completed_at,
                    "last_scan_status": "completed",
                    "latest_summary": summary,
                    "updated_at": completed_at,
                }
            },
        )
        _write_audit(
            organisation_id=organisation_id,
            source_id=source_id,
            user_id=user_id,
            action="DATABASE_SCAN_COMPLETED",
            status="SUCCESS",
            details=summary,
        )

        saved_run = database_scan_runs_collection.find_one({"id": run_id}, {"_id": 0})
        return {
            "source": _public_source(
                _get_source_document(organisation_id, source_id)
            ),
            "run": _public_run(saved_run or run),
            "summary": summary,
            "warnings": list(scan_result.get("warnings", [])),
            "findings": findings,
        }

    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        safe_message = str(exc)
    except Exception:
        # Do not return or log unknown driver exception text because it can contain sensitive infrastructure details.
        safe_message = "Database scan failed unexpectedly. Check backend logs and source configuration."

    failed_at = _now()
    database_scan_runs_collection.update_one(
        {"id": run_id},
        {
            "$set": {
                "status": "FAILED",
                "completed_at": failed_at,
                "error": safe_message,
            }
        },
    )
    database_sources_collection.update_one(
        _source_filter(organisation_id, source_id),
        {"$set": {"last_attempt_at": failed_at, "last_scan_status": "failed", "updated_at": failed_at}},
    )
    _write_audit(
        organisation_id=organisation_id,
        source_id=source_id,
        user_id=user_id,
        action="DATABASE_SCAN_COMPLETED",
        status="FAILED",
        details={"message": safe_message},
    )
    raise DatabaseServiceError(safe_message)


def list_database_findings(
    *,
    organisation_id: str,
    source_id: str,
    limit: int = 500,
) -> dict[str, Any]:
    source = _get_source_document(organisation_id, source_id)
    safe_limit = max(1, min(int(limit), 1000))
    findings = list(
        database_findings_collection.find(
            {"organisation_id": organisation_id, "source_id": source_id},
            {"_id": 0},
        )
        .sort([("risk_rank", -1), ("table", 1), ("column", 1), ("pii_type", 1)])
        .limit(safe_limit)
    )
    return {"source": _public_source(source), "findings": findings}


def list_database_scan_runs(
    *,
    organisation_id: str,
    source_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    _get_source_document(organisation_id, source_id)
    safe_limit = max(1, min(int(limit), 100))
    runs = database_scan_runs_collection.find(
        {"organisation_id": organisation_id, "source_id": source_id},
        {"_id": 0},
    ).sort("started_at", -1).limit(safe_limit)
    return [_public_run(run) for run in runs]


def delete_update_database_source(
    *,
    organisation_id: str,
    source_id: str,
    user_id: str,
    identifier: str,
    action: str,
    new_value: str | None = None,
) -> dict[str, Any]:
    source = _get_source_document(organisation_id, source_id)
    config = dict(source["config"])
    config["organisation_id"] = organisation_id

    # Preserve the original action for audit logging before any internal mapping.
    original_action = action

    try:
        # manage_database_data will map REDACT and MASK to UPDATE with sentinel values.
        result = manage_database_data(config, identifier, action, new_value)
        _write_audit(
            organisation_id=organisation_id,
            source_id=source_id,
            user_id=user_id,
            action=f"DATABASE_{original_action}_COMPLETED",
            status="SUCCESS",
            details={
                "identifier": identifier,
                "new_value": new_value,
                "impacted_locations": result.get("impacted_locations", 0),
                "impacted_rows": result.get("impacted_rows", 0),
            },
        )
        return result
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        _write_audit(
            organisation_id=organisation_id,
            source_id=source_id,
            user_id=user_id,
            action=f"DATABASE_{original_action}_COMPLETED",
            status="FAILED",
            details={"message": str(exc)},
        )
        raise DatabaseServiceError(str(exc))
    except Exception as exc:
        _write_audit(
            organisation_id=organisation_id,
            source_id=source_id,
            user_id=user_id,
            action=f"DATABASE_{original_action}_COMPLETED",
            status="FAILED",
            details={"message": str(exc)},
        )
        raise DatabaseServiceError("Database edit failed unexpectedly.")
