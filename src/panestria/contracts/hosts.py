"""Hostname comparison in the form a browser resolves and shows the owner."""

from __future__ import annotations

import idna


def ascii_host(hostname: str) -> str:
    """Return the lower-case ASCII host for ``hostname``.

    Internationalized names use IDNA2008 with UTS46 non-transitional mapping, as
    current browsers do. The IDNA2003 codec would fold, for example, ``fa\\u00df.de``
    to ``fass.de`` and attribute a fetch to a different host than the one shown.
    ASCII names and IP literals are returned unchanged apart from case. Invalid
    names raise ``UnicodeError``.
    """
    if hostname.isascii():
        return hostname.lower()
    return idna.encode(hostname, uts46=True, transitional=False).decode("ascii").lower()
