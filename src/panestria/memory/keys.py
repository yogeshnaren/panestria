"""Scoped OS Secret Service keys, without prompts, fallback or plaintext logs."""

from __future__ import annotations

import hmac
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from itertools import islice
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, SecretBytes

_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class KeyStoreUnavailable(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ProfileKeyHandle(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    owner_id: str = Field(pattern=_UUID)
    project_id: str = Field(pattern=_UUID)
    profile_id: str = Field(pattern=_UUID)
    key_id: str = Field(pattern=_UUID)

    def attributes(self) -> dict[str, str]:
        return {"application": "panestria", "purpose": "profile-key-v1", **self.model_dump()}


class ProfileKeyStore(Protocol):
    def load(self, handle: ProfileKeyHandle) -> SecretBytes: ...


if sys.platform == "linux":
    import secretstorage
    from jeepney.io.blocking import DBusConnection, get_bus, prep_socket  # type: ignore[import-untyped]
    from jeepney.low_level import Message  # type: ignore[import-untyped]
    from secretstorage.collection import COLLECTION_IFACE, Collection
    from secretstorage.item import Item
    from secretstorage.util import DBusAddressWrapper, format_secret, open_session

    class _BoundedConnection(DBusConnection):  # type: ignore[misc]
        def __init__(self, deadline: float) -> None:
            self.deadline = deadline
            sock = prep_socket(get_bus("SESSION"), timeout=max(0.001, deadline - time.monotonic()))
            try:
                super().__init__(sock)
            except Exception:
                if hasattr(self, "selector"):
                    self.close()
                sock.close()
                raise

        def send_and_get_reply(self, message: Message, *, timeout: float | None = None) -> Message:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            bound = remaining if timeout is None else min(remaining, timeout)
            self.sock.settimeout(bound)
            return super().send_and_get_reply(message, timeout=bound)


class SecretServiceProfileKeys:
    """Explicit setup provisions handles; ordinary vault writes can only load."""

    def __init__(self, *, timeout_seconds: float = 3.0) -> None:
        if not 0.1 <= timeout_seconds <= 5.0:
            raise ValueError("invalid_key_store_timeout")
        self.timeout_seconds = timeout_seconds

    @contextmanager
    def _collection(self) -> Iterator[Collection]:
        if sys.platform != "linux":
            raise KeyStoreUnavailable("key_store_unsupported")
        try:
            with _BoundedConnection(time.monotonic() + self.timeout_seconds) as connection:
                # This API never creates a collection or chooses temporary storage.
                collection = secretstorage.get_collection_by_alias(connection, "default")
                if collection.collection_path == "/org/freedesktop/secrets/collection/session":
                    raise KeyStoreUnavailable("key_store_temporary")
                if collection.is_locked():
                    raise KeyStoreUnavailable("key_store_locked")
                session = open_session(connection)
                if not session.encrypted:
                    raise KeyStoreUnavailable("key_store_transport_unqualified")
                collection.session = session
                yield collection
        except KeyStoreUnavailable:
            raise
        except TimeoutError:
            raise KeyStoreUnavailable("key_store_timeout") from None
        except Exception:
            # Third-party exception text can contain data; expose only fixed codes.
            raise KeyStoreUnavailable("key_store_unavailable") from None

    def _item(self, collection: Collection, handle: ProfileKeyHandle) -> Item | None:
        attributes = handle.attributes()
        items = list(islice(collection.search_items(attributes), 2))
        if len(items) > 1:
            raise KeyStoreUnavailable("key_handle_ambiguous")
        if not items:
            return None
        item = items[0]
        if item.is_locked():
            raise KeyStoreUnavailable("key_store_locked")
        if item.get_attributes() != attributes:
            raise KeyStoreUnavailable("key_scope_mismatch")
        return item

    @staticmethod
    def _secret(item: Item) -> SecretBytes:
        value = item.get_secret()
        if type(value) is not bytes or len(value) != 32:
            raise KeyStoreUnavailable("key_material_invalid")
        return SecretBytes(value)

    def load(self, handle: ProfileKeyHandle) -> SecretBytes:
        with self._collection() as collection:
            item = self._item(collection, handle)
            if item is None:
                raise KeyStoreUnavailable("key_handle_missing")
            return self._secret(item)

    def provision(self, handle: ProfileKeyHandle) -> None:
        with self._collection() as collection:
            existing = self._item(collection, handle)
            if existing is not None:
                self._secret(existing)
                return
            if collection.session is None or not collection.session.encrypted:
                raise KeyStoreUnavailable("key_store_transport_unqualified")
            key = SecretBytes(AESGCM.generate_key(bit_length=256))
            wrapped = format_secret(collection.session, key.get_secret_value(), "application/octet-stream")
            properties = {
                "org.freedesktop.Secret.Item.Label": ("s", "Panestria profile key"),
                "org.freedesktop.Secret.Item.Attributes": ("a{ss}", handle.attributes()),
            }
            # A narrow non-prompting use of the pinned upstream D-Bus wrapper.
            # Never call the high-level create_item(), which can execute a prompt.
            service = DBusAddressWrapper(collection.collection_path, COLLECTION_IFACE, collection.connection)
            path, prompt = service.call("CreateItem", "a{sv}(oayays)b", properties, wrapped, False)
            if not isinstance(path, str) or not path.startswith(collection.collection_path + "/") or prompt != "/":
                raise KeyStoreUnavailable("key_creation_unknown")
            created = self._item(collection, handle)
            if created is None or not hmac.compare_digest(
                self._secret(created).get_secret_value(), key.get_secret_value()
            ):
                raise KeyStoreUnavailable("key_creation_unknown")
