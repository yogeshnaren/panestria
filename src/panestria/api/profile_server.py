"""Explicit qualified personal-mode launcher, with no default service enablement."""

import resource
from pathlib import Path

from panestria.api.local_server import serve_local
from panestria.api.routes.profiles import ProfileApi
from panestria.config_profile_service import load_profile_service
from panestria.memory.keys import SecretServiceProfileKeys
from panestria.memory.profile_runtime import QualifiedProfileKeys
from panestria.memory.vault import ProfileVault


def serve_profiles(path: Path, *, restricted_offline: bool) -> None:
    from panestria.config_local import LocalApplicationRejected

    if restricted_offline is not True:
        raise LocalApplicationRejected("explicit_restricted_offline_intent_required")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    config, _, _ = load_profile_service(path)
    keys = QualifiedProfileKeys(
        config.qualification_directory, config.qualification_sha256, config.key_handles, SecretServiceProfileKeys()
    )
    # Verify before opening a listener or starting the owned model. Loading only
    # checks existing keys; it cannot provision or unlock the owner's keyring.
    keys.validate()
    for handle in config.key_handles:
        keys.load(handle)
    serve_local(config.local_config, profiles=ProfileApi(ProfileVault(keys, enabled=True)))
