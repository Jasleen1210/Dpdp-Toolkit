from typing import Literal, Optional

from pydantic import BaseModel, Field


class DatabaseSourceCreate(BaseModel):
    """Safe source-registration data sent from the browser to the backend."""

    organisation_id: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=2, max_length=120)
    engine: Literal["sqlite", "postgres"]

    # SQLite: relative path under DB_SQLITE_ROOT only.
    sqlite_path: Optional[str] = Field(default=None, max_length=260)

    # PostgreSQL: password is intentionally absent.
    postgres_host: Optional[str] = Field(default=None, max_length=255)
    postgres_port: Optional[int] = Field(default=5432, ge=1, le=65535)
    postgres_database: Optional[str] = Field(default=None, max_length=120)
    postgres_username: Optional[str] = Field(default=None, max_length=120)
    password_env_var: Optional[str] = Field(default=None, max_length=128)
    sslmode: Literal["disable", "prefer", "require", "verify-ca", "verify-full"] = "require"


class DatabaseDataManageRequest(BaseModel):
    """Payload to redact or delete data by identifier in a database."""
    identifier: str = Field(min_length=1)
    action: Literal["UPDATE", "DELETE"]
    new_value: Optional[str] = Field(default=None)