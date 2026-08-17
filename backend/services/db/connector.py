from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Mapping


BACKEND_ROOT = Path(__file__).resolve().parents[2]
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_ALLOWED_SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
_ALLOWED_SSL_MODES = {"disable", "prefer", "require", "verify-ca", "verify-full"}


class DatabaseConfigurationError(ValueError):
    """Raised when a source configuration is invalid or unsafe."""


class DatabaseConnectionError(RuntimeError):
    """Raised when a target database cannot be opened safely."""


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise DatabaseConfigurationError(f"{field_name} is required.")
    return text

def quote_identifier(identifier: str) -> str:
    """Quote a table/column/schema name after allowing only simple identifiers."""
    if not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise DatabaseConfigurationError(
            "This MVP supports table, schema, and column names containing only "
            "letters, numbers, and underscores."
        )
    return f'"{identifier}"'


def _configured_sqlite_root() -> Path:
    """Return a controlled directory; relative env paths are relative to backend/."""
    configured = os.getenv("DB_SQLITE_ROOT", "demo_data").strip() or "demo_data"
    configured_path = Path(configured).expanduser()
    root = configured_path if configured_path.is_absolute() else BACKEND_ROOT / configured_path
    return root.resolve()


def validate_sqlite_relative_path(value: Any) -> str:
    """Allow only a relative .db/.sqlite/.sqlite3 path below DB_SQLITE_ROOT."""
    raw_path = _required_text(value, "sqlite_path").replace("\\", "/")

    if raw_path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:/", raw_path):
        raise DatabaseConfigurationError(
            "sqlite_path must be relative to DB_SQLITE_ROOT, not an absolute path."
        )

    path = Path(raw_path)
    if ".." in path.parts:
        raise DatabaseConfigurationError("sqlite_path cannot contain '..'.")

    if path.suffix.lower() not in _ALLOWED_SQLITE_SUFFIXES:
        raise DatabaseConfigurationError(
            "sqlite_path must end in .db, .sqlite, or .sqlite3."
        )

    return path.as_posix()


def resolve_sqlite_database_path(relative_path: str) -> Path:
    """Resolve a source file and prove it remains inside the approved root folder."""
    root = _configured_sqlite_root()
    candidate = (root / relative_path).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DatabaseConfigurationError(
            "SQLite database path is outside DB_SQLITE_ROOT."
        ) from exc

    if not candidate.is_file():
        raise DatabaseConfigurationError(
            f"SQLite database '{relative_path}' was not found inside DB_SQLITE_ROOT."
        )

    return candidate


def validate_source_config(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Convert an API payload into the safe configuration stored for a source."""
    engine = _required_text(payload.get("engine"), "engine").lower()

    if engine == "sqlite":
        return {
            "engine": "sqlite",
            "sqlite_path": validate_sqlite_relative_path(payload.get("sqlite_path")),
        }

    if engine != "postgres":
        raise DatabaseConfigurationError("Only sqlite and postgres are supported in this phase.")

    port_value = payload.get("postgres_port", 5432)
    try:
        port = int(port_value)
    except (TypeError, ValueError) as exc:
        raise DatabaseConfigurationError("postgres_port must be a valid number.") from exc

    if not 1 <= port <= 65535:
        raise DatabaseConfigurationError("postgres_port must be between 1 and 65535.")

    password_env_var = _required_text(payload.get("password_env_var"), "password_env_var")
    if not _ENVIRONMENT_NAME_PATTERN.fullmatch(password_env_var):
        raise DatabaseConfigurationError(
            "password_env_var must be an uppercase environment-variable name."
        )
    if not password_env_var.startswith("DPDP_DB_"):
        raise DatabaseConfigurationError(
            "password_env_var must start with DPDP_DB_ so DB secrets stay clearly separated."
        )

    sslmode = str(payload.get("sslmode") or "require").strip().lower()
    if sslmode not in _ALLOWED_SSL_MODES:
        raise DatabaseConfigurationError("Unsupported PostgreSQL sslmode.")

    return {
        "engine": "postgres",
        "host": _required_text(payload.get("postgres_host"), "postgres_host"),
        "port": port,
        "database": _required_text(payload.get("postgres_database"), "postgres_database"),
        "username": _required_text(payload.get("postgres_username"), "postgres_username"),
        "password_env_var": password_env_var,
        "sslmode": sslmode,
    }


def connection_label(config: Mapping[str, Any]) -> str:
    """Return safe display text; this intentionally never includes username/password."""
    if config.get("engine") == "sqlite":
        return f"SQLite · {config.get('sqlite_path', 'unknown')}"

    return (
        f"PostgreSQL · {config.get('host', 'unknown')}:{config.get('port', 5432)}"
        f"/{config.get('database', 'unknown')}"
    )


def credential_is_configured(config: Mapping[str, Any]) -> bool:
    """For PostgreSQL, tell the owner whether the named backend secret currently exists."""
    if config.get("engine") == "sqlite":
        return True
    return bool(os.getenv(str(config.get("password_env_var", ""))).strip())


def open_read_only_connection(config: Mapping[str, Any]):
    """Open one SQLite or PostgreSQL connection without any write capability in scanner code."""
    engine = config.get("engine")

    if engine == "sqlite":
        database_path = resolve_sqlite_database_path(str(config["sqlite_path"]))
        try:
            # SQLite URI mode=ro prevents creation/writes. query_only is a second guard.
            connection = sqlite3.connect(
                f"{database_path.as_uri()}?mode=ro",
                uri=True,
                timeout=5,
            )
            connection.execute("PRAGMA query_only = ON")
            return connection
        except sqlite3.Error as exc:
            raise DatabaseConnectionError("Could not open the SQLite database in read-only mode.") from exc

    if engine == "postgres":
        password_env_var = str(config["password_env_var"])
        password = os.getenv(password_env_var, "").strip()
        if not password:
            raise DatabaseConfigurationError(
                f"The backend environment variable '{password_env_var}' is missing or empty."
            )

        try:
            import psycopg
        except ImportError as exc:
            raise DatabaseConfigurationError(
                "PostgreSQL support is not installed. Install psycopg[binary]."
            ) from exc

        try:
            connection = psycopg.connect(
                host=config["host"],
                port=config["port"],
                dbname=config["database"],
                user=config["username"],
                password=password,
                sslmode=config["sslmode"],
                connect_timeout=5,
                autocommit=False,
            )
            # This transaction-level guard supplements the database account's SELECT-only grants.
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            return connection
        except Exception as exc:
            raise DatabaseConnectionError(
                "Could not connect to PostgreSQL using the configured read-only account."
            ) from exc

    raise DatabaseConfigurationError("Unsupported database engine.")


def open_write_connection(config: Mapping[str, Any]):
    """Open one SQLite or PostgreSQL connection with write capability for remediation."""
    engine = config.get("engine")

    if engine == "sqlite":
        database_path = resolve_sqlite_database_path(str(config["sqlite_path"]))
        try:
            connection = sqlite3.connect(
                database_path.as_posix(),
                timeout=5,
            )
            return connection
        except sqlite3.Error as exc:
            raise DatabaseConnectionError("Could not open the SQLite database for writing.") from exc

    if engine == "postgres":
        password_env_var = str(config["password_env_var"])
        password = os.getenv(password_env_var, "").strip()
        if not password:
            raise DatabaseConfigurationError(
                f"The backend environment variable '{password_env_var}' is missing or empty."
            )

        try:
            import psycopg
        except ImportError as exc:
            raise DatabaseConfigurationError(
                "PostgreSQL support is not installed. Install psycopg[binary]."
            ) from exc

        try:
            connection = psycopg.connect(
                host=config["host"],
                port=config["port"],
                dbname=config["database"],
                user=config["username"],
                password=password,
                sslmode=config["sslmode"],
                connect_timeout=5,
                autocommit=False,
            )
            return connection
        except Exception as exc:
            raise DatabaseConnectionError(
                "Could not connect to PostgreSQL for writing."
            ) from exc

    raise DatabaseConfigurationError("Unsupported database engine.")


def close_connection(connection: Any) -> None:
    """End a read transaction without committing anything, then close the connection."""
    if connection is None:
        return

    try:
        connection.rollback()
    except Exception:
        pass

    try:
        connection.close()
    except Exception:
        pass