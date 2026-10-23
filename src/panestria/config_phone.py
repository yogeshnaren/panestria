"""Explicit private TLS observer settings; no network or credential provisioning."""

import ipaddress
import os
import stat
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError, field_validator

from panestria.config_activity import ActivitySettings
from panestria.config_local import LocalApplicationRejected, read_private

PRIVATE_V4 = tuple(
    ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8")
)


def private_ip(value: str) -> bool:
    try:
        ip = ipaddress.IPv4Address(value)
        return str(ip) == value and any(ip in network for network in PRIVATE_V4)
    except ipaddress.AddressValueError:
        return False


class PhoneSettings(ActivitySettings):
    enabled: bool = False
    bind_address: str
    allowed_clients: tuple[str, ...] = Field(min_length=1, max_length=8)
    certificate_file: Path
    key_file: Path

    @field_validator("bind_address")
    @classmethod
    def private_bind(cls, value: str) -> str:
        if not private_ip(value):
            raise ValueError("private_literal_ipv4_required")
        return value

    @field_validator("allowed_clients")
    @classmethod
    def private_clients(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or not all(private_ip(v) for v in values):
            raise ValueError("private_literal_clients_required")
        return values

    @property
    def origin(self) -> str:
        return f"https://{self.bind_address}:{self.bind_port}"


def load_phone_settings(path: Path) -> tuple[PhoneSettings, SecretStr]:
    try:
        if not path.is_absolute() or path.resolve() != path:
            raise LocalApplicationRejected("phone_configuration_path_invalid")
        parent = path.parent.stat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077:
            raise LocalApplicationRejected("local_directory_must_be_private")
        config = PhoneSettings.model_validate_json(read_private(path, 8192))
        if not config.enabled:
            raise LocalApplicationRejected("phone_disabled")
        if config.token_file != path.parent / "activity.token":
            raise LocalApplicationRejected("activity_token_path_invalid")
        import re

        token = read_private(config.token_file, 256).decode("ascii").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token) is None:
            raise LocalApplicationRejected("invalid_local_token")
        for selected in (config.certificate_file, config.key_file):
            if not selected.is_absolute() or selected.resolve() != selected:
                raise LocalApplicationRejected("phone_tls_path_invalid")
            read_private(selected, 65536)
        return config, SecretStr(token)
    except (ValidationError, UnicodeError, OSError):
        raise LocalApplicationRejected("invalid_phone_configuration") from None
