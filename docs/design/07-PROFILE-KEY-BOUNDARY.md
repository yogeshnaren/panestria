# Profile key boundary

This is a bounded AOS-011-S5 foundation. It does not enable profile storage or
certify the whole vault. The trusted local broker reads scoped opaque handles;
workers, model payloads, database rows, backups and logs never receive keys.
Host-administrator compromise remains outside this isolation claim.

Reuse investigation follows REA's direct-source path: inspect the complete
upstream APIs, pin dependencies and adapt the smallest needed boundary.
[SecretStorage 3.5.0 source](https://github.com/mitya57/secretstorage/tree/3.5.0)
is BSD-3-Clause; [cryptography 50.0.2](https://pypi.org/project/cryptography/50.0.2/)
uses Apache-2.0 OR BSD-3-Clause. Jeepney 0.9.0 supplies the pinned D-Bus transport.
No source tree is copied or independently implemented cryptography introduced.

Important upstream findings: get_default_collection() can create a collection,
get_any_collection() can choose temporary session storage, synchronous unlock
can wait for UI, and create_item() may execute a prompt. Automatic broker
operations must do none of these. Use an existing explicit default alias, deny
locked/missing stores, require an encrypted Secret Service session, and inspect
the CreateItem reply without executing prompts. Use the library's session/secret
formatting instead of rewriting its cryptography. Bound the complete operation
and each D-Bus call; close connections on every path.

A handle binds owner, project, profile and random key identity. Search only its
exact application/purpose/scope attributes. Reject absent, duplicated, locked,
wrong-scope or malformed keys. Provisioning is an explicit local setup action
separate from database writes; it is idempotent for an existing valid handle,
never replaces a key, and never silently retries an ambiguous creation. A
duplicate race fails closed rather than selecting one secret. No key deletion,
keyring unlock, collection creation, file/env fallback or unrelated secret
enumeration is part of this adapter.

Live investigation on GNOME Keyring 40.0 found that omitting `xdg:schema` can
intermittently add the generic schema after creation. Declare the explicit
`org.panestria.ProfileKey.v1` attribute on both creation and lookup, retaining
exact attribute equality instead of ignoring unexpected fields. This follows
the [Secret Service schema convention](https://gnome.pages.gitlab.gnome.org/libsecret/struct.Schema.html).

Test fake transports for negative paths, but use actual cryptography. Required
OS conformance will use an isolated D-Bus/keyring session, synthetic secret and
temporary XDG directories, with no modification to the owner's collection.
That evidence is distinct from unit coverage. The profile vault, key rotation,
encrypted restore, suppression and context selection are subsequent work.

References: [collection API](https://secretstorage.readthedocs.io/en/latest/collection.html),
[AEAD](https://cryptography.io/en/50.0.0/hazmat/primitives/aead/).
