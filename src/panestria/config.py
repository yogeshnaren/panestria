"""Strict synthetic-profile settings.

Environment names, process prefix ``PANESTRIA_``:

- ``PANESTRIA_SCHEMA_VERSION``
- ``PANESTRIA_PROFILE``
- ``PANESTRIA_BIND_HOST``
- ``PANESTRIA_BIND_PORT``
- ``PANESTRIA_READINESS_BUDGET_MS``
- ``PANESTRIA_DATABASE_URL``

This module reads the process environment only. It does not load ``.env``.

Database URL policy for ``SYNTHETIC_DEV``:

- scheme ``postgresql`` or ``postgresql+psycopg``
- username and password required; decoded password length at least 8
- host is a hostname, IPv4 address, or bracketed IPv6 address
- port may be omitted; when present it is an integer from 1 to 65535
- path is one database name; query and fragment are rejected
- a password that is exactly a public health reason code is rejected

Malformed URLs, including broken IPv6 brackets and non-numeric ports, are
``invalid_database_url``. Error text does not include the URL or password.
"""

from __future__ import annotations

import ipaddress
import os
from typing import Literal, Self
from urllib.parse import unquote, urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOOPBACK_V4 = ipaddress.ip_network("127.0.0.0/8")
_LOOPBACK_V6 = ipaddress.IPv6Address("::1")
_DATABASE_SCHEMES = frozenset({"postgresql", "postgresql+psycopg"})
_KNOWN_ENV = frozenset(
    {
        "PANESTRIA_SCHEMA_VERSION",
        "PANESTRIA_PROFILE",
        "PANESTRIA_BIND_HOST",
        "PANESTRIA_BIND_PORT",
        "PANESTRIA_READINESS_BUDGET_MS",
        "PANESTRIA_DATABASE_URL",
    }
)
PUBLIC_HEALTH_REASONS = frozenset(
    {
        "capacity_unknown",
        "database_unavailable",
        "deadline_exceeded",
        "not_implemented",
        "not_probed",
        "probe_busy",
        "probe_failed",
        "ready",
    }
)
_SAFE_DATABASE_MESSAGE = "database URL is not a supported PostgreSQL URL"


class ProfileRejected(Exception):
    """Non-retryable settings denial. The message never contains secret material."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        self.retryable = False
        super().__init__(message)


class ValidatedSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    profile: Literal["SYNTHETIC_DEV"]
    bind_host: str
    bind_port: int = Field(ge=1, le=65535)
    readiness_budget_ms: int = Field(ge=50, le=2000)
    database_url: SecretStr

    @model_validator(mode="after")
    def _enforce_profile(self) -> Self:
        if not _is_literal_loopback(self.bind_host):
            raise ValueError("bind host is not a literal loopback address")
        if not _valid_database_url(self.database_url.get_secret_value()):
            raise ValueError(_SAFE_DATABASE_MESSAGE)
        return self

    def secret_material(self) -> tuple[str, ...]:
        """Encoded URL plus decoded password forms. Public reason codes are omitted."""
        url = self.database_url.get_secret_value()
        forms = [url]
        try:
            password = urlsplit(url).password or ""
        except ValueError:
            password = ""
        decoded = unquote(password)
        decoded_twice = unquote(decoded)
        forms.extend((password, decoded, decoded_twice))
        unique: list[str] = []
        for value in forms:
            if len(value) < 8 or value in PUBLIC_HEALTH_REASONS or value in unique:
                continue
            unique.append(value)
        return tuple(unique)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PANESTRIA_",
        extra="forbid",
        hide_input_in_errors=True,
        env_file=None,
    )

    schema_version: int = 1
    profile: str = "SYNTHETIC_DEV"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    readiness_budget_ms: int = 500
    database_url: SecretStr

    @field_validator("schema_version", "bind_port", "readiness_budget_ms", mode="before")
    @classmethod
    def reject_bool_and_non_int(cls, value: object) -> object:
        if isinstance(value, bool) or isinstance(value, float):
            raise ValueError("integer value required")
        return value

    def validate_profile(self) -> ValidatedSettings:
        if self.schema_version != 1:
            raise ProfileRejected("invalid_schema_version", "schema_version must be 1")
        if self.profile != "SYNTHETIC_DEV":
            raise ProfileRejected("invalid_profile", "profile is not enabled")
        if not isinstance(self.bind_port, int) or not 1 <= self.bind_port <= 65535:
            raise ProfileRejected("invalid_bind", "bind port is outside 1-65535")
        if not _is_literal_loopback(self.bind_host):
            raise ProfileRejected("invalid_bind", "bind host is not a literal loopback address")
        if not 50 <= self.readiness_budget_ms <= 2000:
            raise ProfileRejected("invalid_settings", "readiness budget is outside 50-2000 ms")
        try:
            database_ok = _valid_database_url(self.database_url.get_secret_value())
        except ValueError:
            database_ok = False
        if not database_ok:
            raise ProfileRejected("invalid_database_url", _SAFE_DATABASE_MESSAGE)
        try:
            return ValidatedSettings(
                schema_version=1,
                profile="SYNTHETIC_DEV",
                bind_host=self.bind_host,
                bind_port=self.bind_port,
                readiness_budget_ms=self.readiness_budget_ms,
                database_url=self.database_url,
            )
        except ValidationError:
            raise ProfileRejected("invalid_settings", "settings rejected") from None


def load_settings() -> ValidatedSettings:
    """Load and validate process settings. Errors omit input values."""
    if any(key.startswith("PANESTRIA_") and key not in _KNOWN_ENV for key in os.environ):
        raise ProfileRejected("invalid_settings", "settings rejected")
    try:
        return Settings().validate_profile()
    except ProfileRejected:
        raise
    except ValueError:
        raise ProfileRejected("invalid_database_url", _SAFE_DATABASE_MESSAGE) from None
    except ValidationError:
        raise ProfileRejected("invalid_settings", "settings rejected") from None


def _is_literal_loopback(host: str) -> bool:
    if host == "" or host != host.strip():
        return False
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(parsed, ipaddress.IPv6Address):
        return parsed == _LOOPBACK_V6 and not parsed.ipv4_mapped
    return parsed in _LOOPBACK_V4


def _valid_database_url(url: str) -> bool:
    if url != url.strip() or any(character.isspace() for character in url):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme not in _DATABASE_SCHEMES:
        return False
    if parts.hostname in (None, "") or parts.query or parts.fragment:
        return False
    if port is not None and not 1 <= port <= 65535:
        return False
    if not parts.username or parts.password is None:
        return False
    raw_password = parts.password
    decoded = unquote(raw_password)
    if len(decoded) < 8 or any(character.isspace() for character in decoded):
        return False
    if raw_password in PUBLIC_HEALTH_REASONS or decoded in PUBLIC_HEALTH_REASONS:
        return False
    database_name = parts.path.removeprefix("/")
    if "/" in database_name or not database_name.replace("_", "").isalnum():
        return False
    if not database_name or not database_name[0].isalpha():
        return False
    return True
