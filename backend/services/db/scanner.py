from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any, Iterable, Mapping

from backend.services.pii_detection import detect_pii

try:
    from backend.services.db.connector import (
        DatabaseConfigurationError,
        close_connection,
        open_read_only_connection,
        quote_identifier,
    )
except ImportError:
    from backend.services.db.connector import (
        DatabaseConfigurationError,
        close_connection,
        open_read_only_connection,
        quote_identifier,
    )


# Ordered from most specific to least specific. First matching rule wins.
_METADATA_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Aadhaar", re.compile(r"(?:^|_)(?:aadhaar|aadhar|uidai|uid(?:_?(?:no|number))?)(?:_|$)")),
    ("PAN", re.compile(r"(?:^|_)(?:pan|pan_card|pan_no|pan_number)(?:_|$)")),
    ("Credit Card", re.compile(r"(?:^|_)(?:card_no|card_number|credit_card|debit_card|cc_number)(?:_|$)")),
    ("Email", re.compile(r"(?:^|_)(?:email|e_mail|email_id|mail_id)(?:_|$)")),
    ("Phone", re.compile(r"(?:^|_)(?:phone|mobile|cell|telephone|tel|contact_no|contact_number)(?:_|$)")),
    ("IP Address", re.compile(r"(?:^|_)(?:ip_address|ipaddr|ipv4|ipv6)(?:_|$)")),
    ("Date of Birth", re.compile(r"(?:^|_)(?:dob|date_of_birth|birth_date|birthdate)(?:_|$)")),
    ("Address", re.compile(r"(?:^|_)(?:address|addr|street|pincode|zip|postal_code)(?:_|$)")),
    ("Name", re.compile(r"(?:^|_)(?:full_name|first_name|last_name|fname|lname|customer_name|employee_name|person_name)(?:_|$)")),
)

_RISK_BY_TYPE = {
    "Aadhaar": ("critical", 4),
    "PAN": ("critical", 4),
    "Credit Card": ("critical", 4),
    "Email": ("high", 3),
    "Phone": ("high", 3),
    "Address": ("high", 3),
    "Date of Birth": ("high", 3),
    "Name": ("medium", 2),
    "IP Address": ("medium", 2),
}

_ACTION_BY_TYPE = {
    "Aadhaar": "redact",
    "PAN": "redact",
    "Credit Card": "redact",
    "Email": "mask",
    "Phone": "mask",
    "Address": "redact",
    "Date of Birth": "redact",
    "Name": "mask",
    "IP Address": "mask",
}


def _environment_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _normalise_column_name(column_name: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", column_name)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value.lower()


def _metadata_type(column_name: str) -> str | None:
    normalized = _normalise_column_name(column_name)
    for pii_type, pattern in _METADATA_RULES:
        if pattern.search(normalized):
            return pii_type
    return None


def _is_sampleable(data_type: str) -> bool:
    lowered = (data_type or "").lower()
    # Binary data is not converted to text. Everything else is bounded before inspection.
    return not any(token in lowered for token in ("blob", "bytea", "binary", "varbinary", "image"))


def _bounded_text(value: Any) -> str:
    if value is None or isinstance(value, (bytes, bytearray, memoryview)):
        return ""
    text = str(value).strip()
    return text[:4096]


def _data_hit_counts(values: Iterable[Any]) -> Counter[str]:
    """Count how many sampled rows contained each type; raw detector values never leave this function."""
    counts: Counter[str] = Counter()

    for value in values:
        text = _bounded_text(value)
        if not text:
            continue

        types_in_this_value = {
            str(match.get("type"))
            for match in detect_pii(text)
            if match.get("type")
        }
        for pii_type in types_in_this_value:
            counts[pii_type] += 1

    return counts


def _regex_confidence(match_count: int, sample_count: int) -> float:
    if sample_count <= 0:
        return 0.0

    ratio = match_count / sample_count
    if ratio >= 0.80:
        return 0.90
    if ratio >= 0.50:
        return 0.80
    if ratio >= 0.20:
        return 0.65
    return 0.50


def _risk(pii_type: str) -> tuple[str, int]:
    return _RISK_BY_TYPE.get(pii_type, ("medium", 2))


def _recommended_action(pii_type: str) -> str:
    return _ACTION_BY_TYPE.get(pii_type, "review")


def _build_column_findings(
    *,
    engine: str,
    table_name: str,
    column_name: str,
    column_type: str,
    values: list[Any],
) -> list[dict[str, Any]]:
    metadata_type = _metadata_type(column_name)
    hit_counts = _data_hit_counts(values) if _is_sampleable(column_type) else Counter()
    all_types = set(hit_counts)
    if metadata_type:
        all_types.add(metadata_type)

    findings: list[dict[str, Any]] = []
    sample_count = len(values)

    for pii_type in sorted(all_types):
        match_count = int(hit_counts.get(pii_type, 0))
        metadata_hit = pii_type == metadata_type
        regex_hit = match_count > 0

        if metadata_hit and regex_hit:
            method = "metadata+regex"
            confidence = 0.98
        elif metadata_hit:
            method = "metadata"
            confidence = 0.80
        else:
            method = "regex"
            confidence = _regex_confidence(match_count, sample_count)

        risk, risk_rank = _risk(pii_type)
        findings.append(
            {
                "source_type": "database",
                "engine": engine,
                "table": table_name,
                "column": column_name,
                "column_type": column_type or "unknown",
                "location": f"{table_name}.{column_name}",
                "pii_type": pii_type,
                "confidence": confidence,
                "sample_count": sample_count,
                "match_count": match_count,
                "method": method,
                "risk": risk,
                "risk_rank": risk_rank,
                "recommended_action": _recommended_action(pii_type),
            }
        )

    return findings


def _sqlite_table_names(connection: Any, max_tables: int) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows[:max_tables]]


def _scan_sqlite(connection: Any, sample_limit: int, max_tables: int) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    inspected_columns = 0
    sampled_values = 0

    for table_name in _sqlite_table_names(connection, max_tables):
        try:
            quoted_table = quote_identifier(table_name)
            columns = connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()

            for column_info in columns:
                column_name = str(column_info[1])
                column_type = str(column_info[2] or "unknown")
                inspected_columns += 1
                quoted_column = quote_identifier(column_name)

                values: list[Any] = []
                if _is_sampleable(column_type):
                    rows = connection.execute(
                        f"SELECT {quoted_column} FROM {quoted_table} "
                        f"WHERE {quoted_column} IS NOT NULL LIMIT ?",
                        (sample_limit,),
                    ).fetchall()
                    values = [row[0] for row in rows]
                    sampled_values += len(values)

                findings.extend(
                    _build_column_findings(
                        engine="sqlite",
                        table_name=table_name,
                        column_name=column_name,
                        column_type=column_type,
                        values=values,
                    )
                )
        except DatabaseConfigurationError:
            warnings.append("Skipped one SQLite table because its identifier is unsupported by this MVP.")
        except Exception:
            warnings.append("Skipped one SQLite table because it could not be read safely.")

    return {
        "findings": findings,
        "scanned_tables": len(_sqlite_table_names(connection, max_tables)),
        "inspected_columns": inspected_columns,
        "sampled_values": sampled_values,
        "warnings": warnings,
    }


def _postgres_table_names(connection: Any, max_tables: int, allowed_schemas: list[str] | None = None) -> list[tuple[str, str]]:
    with connection.cursor() as cursor:
        if allowed_schemas:
            schema_placeholders = ", ".join(["%s"] * len(allowed_schemas))
            cursor.execute(
                "SELECT table_schema, table_name "
                "FROM information_schema.tables "
                "WHERE table_type = 'BASE TABLE' "
                f"AND table_schema IN ({schema_placeholders}) "
                "ORDER BY table_schema, table_name "
                "LIMIT %s",
                (*allowed_schemas, max_tables),
            )
        else:
            cursor.execute(
                "SELECT table_schema, table_name "
                "FROM information_schema.tables "
                "WHERE table_type = 'BASE TABLE' "
                "AND table_schema = 'public' "
                "ORDER BY table_schema, table_name "
                "LIMIT %s",
                (max_tables,),
            )
        return [(str(row[0]), str(row[1])) for row in cursor.fetchall()]


def _scan_postgres(connection: Any, sample_limit: int, max_tables: int, allowed_schemas: list[str] | None = None) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    inspected_columns = 0
    sampled_values = 0
    tables = _postgres_table_names(connection, max_tables, allowed_schemas=allowed_schemas)

    for schema_name, raw_table_name in tables:
        try:
            quoted_schema = quote_identifier(schema_name)
            quoted_table_name = quote_identifier(raw_table_name)
            qualified_table = f"{quoted_schema}.{quoted_table_name}"
            display_table = f"{schema_name}.{raw_table_name}"

            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT column_name, data_type, udt_name "
                    "FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s "
                    "ORDER BY ordinal_position",
                    (schema_name, raw_table_name),
                )
                columns = cursor.fetchall()

            for column_info in columns:
                column_name = str(column_info[0])
                column_type = str(column_info[1] or column_info[2] or "unknown")
                inspected_columns += 1
                quoted_column = quote_identifier(column_name)

                values: list[Any] = []
                if _is_sampleable(column_type):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"SELECT {quoted_column}::text FROM {qualified_table} "
                            f"WHERE {quoted_column} IS NOT NULL LIMIT %s",
                            (sample_limit,),
                        )
                        values = [row[0] for row in cursor.fetchall()]
                    sampled_values += len(values)

                findings.extend(
                    _build_column_findings(
                        engine="postgres",
                        table_name=display_table,
                        column_name=column_name,
                        column_type=column_type,
                        values=values,
                    )
                )
        except DatabaseConfigurationError:
            warnings.append("Skipped one PostgreSQL table because its identifier is unsupported by this MVP.")
        except Exception:
            # Do not expose driver details, credentials, or raw values in warnings.
            warnings.append("Skipped one PostgreSQL table because it could not be read safely.")

    return {
        "findings": findings,
        "scanned_tables": len(tables),
        "inspected_columns": inspected_columns,
        "sampled_values": sampled_values,
        "warnings": warnings,
    }


def scan_database(config: Mapping[str, Any], allowed_schemas: list[str] | None = None) -> dict[str, Any]:
    """Scan one saved source. The returned object contains aggregate metadata only."""
    sample_limit = _environment_int("DB_SCAN_SAMPLE_LIMIT", 50, 1, 500)
    max_tables = _environment_int("DB_SCAN_MAX_TABLES", 100, 1, 500)
    connection = open_read_only_connection(config)

    try:
        if config.get("engine") == "sqlite":
            result = _scan_sqlite(connection, sample_limit, max_tables)
        elif config.get("engine") == "postgres":
            result = _scan_postgres(connection, sample_limit, max_tables, allowed_schemas=allowed_schemas)
        else:
            raise DatabaseConfigurationError("Unsupported database engine.")
    finally:
        close_connection(connection)

    result["engine"] = config.get("engine")
    result["sample_limit"] = sample_limit
    result["findings"] = sorted(
        result["findings"],
        key=lambda item: (-int(item["risk_rank"]), item["table"], item["column"], item["pii_type"]),
    )
    return result