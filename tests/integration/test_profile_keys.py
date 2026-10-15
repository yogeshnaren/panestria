"""Negative adapter paths use fake transport; OS qualification is separate."""

from __future__ import annotations

import socket
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from panestria.memory import keys

pytestmark = pytest.mark.skipif(keys.sys.platform != "linux", reason="Linux Secret Service adapter")
SENTINEL = "synthetic-private-error-do-not-log"


def handle() -> keys.ProfileKeyHandle:
    return keys.ProfileKeyHandle(**{field: str(uuid4()) for field in keys.ProfileKeyHandle.model_fields})


class Item:
    def __init__(self, attributes: dict[str, str], secret: bytes = b"s" * 32) -> None:
        self.attributes, self.secret, self.locked = attributes, secret, False

    def is_locked(self):
        return self.locked

    def get_attributes(self):
        return self.attributes

    def get_secret(self):
        return self.secret


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch):
    state = SimpleNamespace(
        items=[],
        closed=0,
        locked=False,
        encrypted=True,
        aliases=[],
        creates=[],
        prompt="/",
        error=None,
        collection_path="/org/freedesktop/secrets/collection/test",
        connection=object(),
        session=None,
    )

    class Connection:
        def __init__(self, deadline):
            assert 0 < deadline - keys.time.monotonic() <= 3

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            state.closed += 1

    def collection(_connection, alias):
        state.aliases.append(alias)
        if state.error:
            raise state.error
        return state

    def create(_path, _interface, _connection):
        assert (_path, _interface, _connection) == (
            state.collection_path,
            keys.COLLECTION_IFACE,
            state.connection,
        )

        def call(method, signature, properties, secret, replace):
            assert method == "CreateItem" and signature == "a{sv}(oayays)b"
            assert replace is False and state.session.encrypted
            state.creates.append(properties)
            state.items.append(Item(properties["org.freedesktop.Secret.Item.Attributes"][1], secret))
            return state.collection_path + "/item1", state.prompt

        return SimpleNamespace(call=call)

    state.is_locked = lambda: state.locked
    state.search_items = lambda attributes: iter(state.items)
    monkeypatch.setattr(keys, "_BoundedConnection", Connection)
    monkeypatch.setattr(keys.secretstorage, "get_collection_by_alias", collection)
    monkeypatch.setattr(keys, "open_session", lambda connection: SimpleNamespace(encrypted=state.encrypted))
    monkeypatch.setattr(keys, "format_secret", lambda session, secret, kind: secret)
    monkeypatch.setattr(keys, "DBusAddressWrapper", create)

    def forbidden(*args, **kwargs):
        raise AssertionError("prompt, collection creation or fallback attempted")

    for name in ("get_default_collection", "get_any_collection", "create_collection", "search_items"):
        monkeypatch.setattr(keys.secretstorage, name, forbidden)
    return state


def test_provision_is_scoped_idempotent_and_never_replaces(transport):
    reference = handle()
    store = keys.SecretServiceProfileKeys()
    store.provision(reference)
    first = store.load(reference)
    store.provision(reference)
    assert first.get_secret_value() == store.load(reference).get_secret_value()
    assert len(first.get_secret_value()) == 32 and "**********" in repr(first)
    assert len(transport.creates) == 1 and transport.closed == 4
    assert transport.items[0].attributes == reference.attributes()
    assert transport.aliases == ["default"] * 4
    assert transport.items[0].secret.hex() not in repr(reference)


@pytest.mark.parametrize("operation", ["load", "provision"])
@pytest.mark.parametrize(
    "fault,code",
    [
        ("locked", "key_store_locked"),
        ("plaintext", "key_store_transport_unqualified"),
        ("temporary", "key_store_temporary"),
        ("ambiguous", "key_handle_ambiguous"),
        ("wrong_scope", "key_scope_mismatch"),
        ("locked_item", "key_store_locked"),
        ("short_key", "key_material_invalid"),
        ("error", "key_store_unavailable"),
        ("timeout", "key_store_timeout"),
    ],
)
def test_fail_closed_before_key_use(transport, operation, fault, code):
    reference = handle()
    item = Item(reference.attributes())
    transport.items = [item]
    if fault == "locked":
        transport.locked = True
    elif fault == "plaintext":
        transport.encrypted = False
    elif fault == "temporary":
        transport.collection_path = "/org/freedesktop/secrets/collection/session"
    elif fault == "ambiguous":
        transport.items.append(item)
    elif fault == "wrong_scope":
        item.attributes = {**reference.attributes(), "owner_id": str(uuid4())}
    elif fault == "locked_item":
        item.locked = True
    elif fault == "short_key":
        item.secret = SENTINEL.encode()
    else:
        transport.error = TimeoutError(SENTINEL) if fault == "timeout" else RuntimeError(SENTINEL)
    with pytest.raises(keys.KeyStoreUnavailable, match=f"^{code}$") as caught:
        getattr(keys.SecretServiceProfileKeys(), operation)(reference)
    assert SENTINEL not in str(caught.value)
    assert transport.closed == 1 and not transport.creates


def test_load_never_provisions_missing_key(transport):
    with pytest.raises(keys.KeyStoreUnavailable, match="^key_handle_missing$"):
        keys.SecretServiceProfileKeys().load(handle())
    assert transport.closed == 1 and not transport.creates


def test_unknown_creation_is_not_retried_or_prompted(transport):
    transport.prompt = "/org/freedesktop/secrets/prompt/owner"
    with pytest.raises(keys.KeyStoreUnavailable, match="^key_creation_unknown$"):
        keys.SecretServiceProfileKeys().provision(handle())
    assert transport.closed == 1 and len(transport.creates) == 1


@pytest.mark.parametrize("field", list(keys.ProfileKeyHandle.model_fields))
def test_handle_rejects_extra_fields_and_noncanonical_identifiers(field):
    reference = handle().model_dump()
    with pytest.raises(ValidationError):
        keys.ProfileKeyHandle(**{**reference, field: SENTINEL})
    with pytest.raises(ValidationError):
        keys.ProfileKeyHandle(**reference, secret=SENTINEL)


@pytest.mark.parametrize("value", [0, -1, 0.09, 5.01, float("nan"), float("inf")])
def test_timeout_is_bounded(value):
    with pytest.raises(ValueError, match="invalid_key_store_timeout"):
        keys.SecretServiceProfileKeys(timeout_seconds=value)


def test_connection_enforces_one_shared_deadline(monkeypatch):
    calls = []
    socket = SimpleNamespace(settimeout=lambda value: calls.append(value))
    monkeypatch.setattr(keys, "get_bus", lambda name: "synthetic-bus")
    monkeypatch.setattr(keys, "prep_socket", lambda address, timeout: socket)
    monkeypatch.setattr(keys.DBusConnection, "__init__", lambda self, sock: setattr(self, "sock", sock))
    monkeypatch.setattr(keys.DBusConnection, "send_and_get_reply", lambda self, message, timeout: timeout)
    clock = iter([10.0, 10.2, 10.5, 11.1])
    monkeypatch.setattr(keys.time, "monotonic", lambda: next(clock))
    connection = keys._BoundedConnection(11.0)
    assert connection.send_and_get_reply(None, timeout=0.1) == pytest.approx(0.1)
    assert connection.send_and_get_reply(None) == pytest.approx(0.5)
    with pytest.raises(TimeoutError):
        connection.send_and_get_reply(None)
    assert calls == pytest.approx([0.1, 0.5])


def test_connection_initialization_failure_closes_socket(monkeypatch):
    closed = []
    socket = SimpleNamespace(close=lambda: closed.append("socket"))
    monkeypatch.setattr(keys, "get_bus", lambda name: "synthetic-bus")
    monkeypatch.setattr(keys, "prep_socket", lambda address, timeout: socket)

    def fail(self, sock):
        raise TimeoutError(SENTINEL)

    monkeypatch.setattr(keys.DBusConnection, "__init__", fail)
    with pytest.raises(TimeoutError):
        keys._BoundedConnection(keys.time.monotonic() + 1)
    assert closed == ["socket"]


def test_real_stalled_bus_authentication_is_bounded(tmp_path):
    address = str(tmp_path / "bus")
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(address)
        listener.listen(1)
        # A connected socket that never completes authentication must time out.
        from unittest.mock import patch

        started = keys.time.monotonic()
        with patch.object(keys, "get_bus", return_value=address), pytest.raises(TimeoutError):
            keys._BoundedConnection(started + 0.2)
        assert keys.time.monotonic() - started < 1
