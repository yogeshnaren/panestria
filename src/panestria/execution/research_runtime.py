"""Source/configuration identity for standalone and joint PUBLIC research runtimes."""

import hashlib
import json
import os
import platform
import ssl
import sys
from pathlib import Path

from panestria.contracts.fetch_connection import FETCH_CONFIGURATION_SHA256
from panestria.contracts.search import LocalSearchSettings
from panestria.policy.research import RESEARCH_PROFILE
from panestria.policy.research_fetch import FETCH_PROFILE
from panestria.policy.search import SEARCH_PROFILE
from panestria.sandbox.profiles import DEFAULT_IMAGE


def _source_sha256() -> str:
    source = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(source.rglob("*.py")):
        digest.update(str(path.relative_to(source)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def search_runtime_versions(settings: LocalSearchSettings) -> dict[str, str]:
    return {
        "profile": SEARCH_PROFILE,
        "source_sha256": _source_sha256(),
        "configuration_sha256": hashlib.sha256(settings.model_dump_json().encode()).hexdigest(),
    }


def fetch_runtime_versions() -> dict[str, str]:
    return {
        "profile": FETCH_PROFILE,
        "source_sha256": _source_sha256(),
        "configuration_sha256": FETCH_CONFIGURATION_SHA256,
        "python": sys.version,
        "openssl": ssl.OPENSSL_VERSION,
        "kernel": platform.release(),
        "reader_image": DEFAULT_IMAGE,
        "uid": str(os.getuid()),
        "gid": str(os.getgid()),
    }


def research_runtime_versions(settings: LocalSearchSettings) -> dict[str, str]:
    # Pin both configurations. A component's immutable admission plan/disclosure
    # still uses that component's hash; the certificate binds the joint runtime.
    settings = LocalSearchSettings.model_validate_json(settings.model_dump_json())
    versions = fetch_runtime_versions()
    components = {
        "profile": RESEARCH_PROFILE,
        "search_configuration_sha256": hashlib.sha256(settings.model_dump_json().encode()).hexdigest(),
        "fetch_configuration_sha256": versions["configuration_sha256"],
    }
    combined = json.dumps(components, sort_keys=True, separators=(",", ":")).encode()
    return {**versions, **components, "configuration_sha256": hashlib.sha256(combined).hexdigest()}
