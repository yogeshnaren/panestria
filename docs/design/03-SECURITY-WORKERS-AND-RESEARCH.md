# Security implementation and live integration boundaries

## Explicit threat and principal boundaries

Host API/kernel/DB are trusted application components under the local owner; model-generated repositories, source pages, skills, provider streams and UI-rendered content are untrusted data. Native vendor authentication is a separate secret-bearing principal. Workers cannot access PostgreSQL credentials, owner home, SSH keys, protected artifact store or protected Git refs. Verifiers cannot access provider auth or network. The HTTP broker is the only public-fetch path. The UI cannot grant its own permissions.

Primary Linux backend proposed for R1: hardened Docker process containers, with a dedicated trusted supervisor owning runtime control. Runtime containers are non-root, no privileged flag, read-only root, drop capabilities, no-new-privileges, explicit tmpfs/output/workspace mounts, PID/memory/CPU/wall/output caps, seccomp default plus tested restrictions. No Docker socket is mounted into any worker. Docker availability/permissions are diagnosed; unsupported environments fail certification, never fall back to host shell. Actual image/UID/OS/network rules are pinned/probed in AOS-008. A separate bwrap/VM backend is not required for this MVP.

| Profile | Read/write | Egress | Secret access |
|---|---|---|---|
| mock-no-network | Synthetic candidate; immutable check bundle read-only | None | None |
| restricted-offline | Scoped data through broker, bounded scratch | None; local inference reached through approved supervisor channel, not arbitrary localhost | None |
| verifier | Candidate read-only + trusted checks read-only, scratch/report output | None | None |
| read-only-research | One raw source read-only; bounded scratch/output channel | Reader none; fetch capability mediated by trusted broker | None |
| scoped-code-edit | Exact sanitized attempt root writable; context read-only | Native inference destinations only, with OS-enforced destination policy | Native harness must prove credential isolation from its tool execution |

A worktree and CLI flags are not OS isolation. Resource limits/network allowlists must be measured from inside the effective process. Route model-provider HTTPS through a trusted egress gateway with allowed hosts/ports and anti-private-IP DNS rules; default direct egress denied. If a native CLI bypasses the gateway or tool restrictions, live capability is not certified. Implement the gateway's enforcement as tested infrastructure, not a prompt or the descriptive egress-preflight script.

## Native CLI authentication is a required compatibility spike

Do not mount a credential volume broadly into an untrusted shell just because the CLI needs login. A single UID that reads a token can generally expose it to code running as that UID. The first live edit profile uses confined native file tools and no arbitrary shell, while a separate no-secret verifier executes reviewed checks. Any required bounded shell tool must cross a tested isolated runner/tool gateway that excludes the credential location/environment. If the installed harness cannot implement that separation, remain in the edit-only profile and record the unmet shell tier; do not mark the full AOS-010 profile certified or widen host access.

This plan deliberately isolates the shell-tier spike instead of pretending a generic credential bind mount is safe. The active-spec requirement for bounded Bash is retained as a separately tested capability. An edit-only pilot can be demonstrated, but G1/R3 acceptance for an enabled shell capability requires that gateway/OS proof. A kernel verifier's safe test invocation does not automatically certify the native shell tool.

**Primary bounded-shell integration candidate:** a kernel-owned MCP tool server bound to one attempt presents only run_registered_check(command_ref, candidate_ref) and returns bounded immutable report references. The server fixes actor/project/attempt context from its instance, ignores client claims of approval, validates the command registry and invokes a separate verifier/command container with no vendor credentials. Arbitrary native shell/code tools are disabled. The CLI receives only an explicit trusted MCP config/endpoint; no repo-controlled server definitions. A Claude safe-mode profile disables MCP and therefore remains edit-only; the shell-capable profile must instead use a tested restricted/explicit-settings/strict-MCP combination with ambient customizations rejected. The installed CLI must prove this config/auth behavior before promotion. Codex must likewise prove native tools cannot bypass the gateway; otherwise that profile is unavailable. No gateway signature or compatibility is presumed from this design.

The MCP server is an internal bounded command bridge for MVP Build, not the post-MVP general external-agent front end. Its executable/image/config hashes are part of the capability manifest. Broker requests are scoped to the current attempt and permit only declared commands/deadlines; invalid or stale refs deny before process launch. Its check results still do not authorize merge or contract changes.

For Claude, inspect exact binary/version/auth status and dedicated config provenance. Current docs describe safe-mode disabling customizations while managed policy hooks can remain, restricted mode with explicit tools and no ambient user/project settings, and permission-prompts none denying unanswered prompts. These are complementary controls, not the sandbox. Probe combined mode/auth behavior; reject unexpected managed hooks/settings. Inject trusted context via the supported prompt-file channel when workspace instructions are disabled. Bare/API mode is not assumed subscription-compatible. No permission bypass flags.

For Codex, use its supported exec/JSONL interface and login status probe, pinned profiles and workspace. Protect local config/auth state from repo content; apply native and outer OS confinement, especially read scopes. Default resume disabled until tested. Current official docs establish the interface; malformed events, version drift, auth/billing mode and actual file/network restrictions still need fixture/live checks. Headless approval suppression is not permission to bypass kernel/OS policy.

## Three-axis policy

Privacy order PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED; unknown label denies pending owner resolution. Derived data inherits maximum sensitivity unless a separately reviewed downgrade exists. Trust certification controls tested runtime/capability envelope per project. Autonomy controls which actions need approval. Capability/OS/provider constraints intersect all three; any denial wins. A model can propose a request, never supply proof that it is authorized.

PolicyRequest contains owner/project/task/attempt, action, capability, data refs/labels, destination, trust/privacy/autonomy versions, budget, current time and intended effect. Permit contains policy_decision_id, scope, expiry and enforcement requirements; ApprovalNeeded is not Permit. Revalidate before every future effect; replaying an old DBOS result cannot renew authorization. Test every axis alone and all sensitive path/destination/action pairs.

## Local API/browser identity

Loopback API starts with one seeded owner and a cryptographically random scoped CLI token stored in a local 0600 file. CLI uses Authorization header; tokens never appear in URLs. Browser obtains a short-lived session through a one-use locally displayed pairing code entered on the loopback page; rate-limit/expire codes and bind pairing to exact permitted Host/Origin. Browser mutations require a per-session CSRF token plus HttpOnly SameSite=Strict session cookie and exact origin. Cookie Secure when HTTPS is enabled; do not claim TLS protection for loopback HTTP. Remote access is disabled in MVP.

Validate Host independently of loopback binding. Origin-bearing requests must match the configured first-party origin; missing Origin is allowed only for authenticated non-browser CLI flow, never as a blanket mutation bypass. Content type/body/rate limits are enforced. R3 serves built UI on the same API origin; development Vite origin is an explicitly separate allowlisted profile, never wildcard CORS. SSE supports cookie auth plus origin checks; CLI uses bearer header. Revocation/expiry stops reconnect and privileged actions. Local malicious same-user software is outside the cookie/bearer protection claim; OS principal isolation is still needed.

## Artifact and Git containment

Canonicalize project roots at owner enrollment; no arbitrary raw download path route. Validate realpath/components/symlinks/hardlinks and file counts/sizes, reject devices/FIFOs. Copy outputs through a trusted ingress broker into a content-addressed protected store, atomic write/rename then hash recheck; DB metadata references only finalized blobs. Crash after blob publish before DB reference leaves an orphan, not a passed task; TTL cleanup checks live refs before deleting. Crash before finalization never exposes a partial evidence blob. Store permissions and labels apply to downloads, logs and UI.

Git worktree management uses a dedicated managed mirror/attempt checkout, disabled hooks/credential helpers/config injection, no original remote credential or writable parent refs. Protect .git indirection and core.hooksPath; test git config include/alternates/submodule/LFS behavior. Submodule/network fetch and unknown filters are off unless independently allowlisted. Protected merge occurs only through the kernel CAS actor into the trusted bare destination; worker Git writes cannot commit the protected action. Tests attempting real host files use synthetic sentinel fixtures, not actual personal secrets.

## SSRF and hostile source defense

Policy denies loopback/private/link-local/metadata/multicast/reserved/non-global addresses, encoded IP forms, unapproved ports/schemes and HTTPS downgrade. Resolve all returned IPv4/IPv6 addresses, reject mixed allowed/denied sets and connect only to a checked address with original SNI/Host/cert verification. Validate redirect targets independently; ignore ambient proxy/env credentials and strip authorization on redirect. Cap compressed/decompressed bytes, charset/extractor work and total time. No direct raw urllib/urlopen convenience path that silently follows redirects/re-resolves unchecked.

Unit tests inject resolver/connector/clock and verify exact pin/TLS/redirect behavior without connecting to the real internet. OS-network tests use isolated fixtures and no host metadata services. Hermetic fake transport does not prove OS confinement; both layers have required cases. Reader/synthesizer receive page text as data and have no send/shell/private filesystem capability. Unsupported PDF/JS/oversized/incomplete tables are labelled incomplete. Render briefs with active HTML disabled and safe URL schemes.

## Concrete evidence required before live authority

Effective mount/process/egress manifest, credential sentinel isolation, malicious repo-config/hook/MCP denial, policy decision IDs, native version/auth/tool profile, signal/cancellation receipt, trusted test bundle hashes and source/privacy attribution. Native login is performed explicitly by the owner through sanctioned tools; no token extraction, account pooling or assumed background consent. Public-web and paid SDK live smokes are separate consented actions when implementing. This design task provisions no secrets.
