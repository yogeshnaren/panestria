# Credential-free native bootstrap in the offline sandbox

After PR89, start from main `07c6298`. The container loopback/private-gateway
transport is separately tested; the native binary/auth process is still not a
certified connected worker. Inspect its pinned version and advertised controls
inside the existing restricted-offline DockerSandbox first. That launcher already
checks effective mounts, nonroot identity, resources and network-none, and stacks
an inherited Linux x86-64 seccomp denial of Internet socket creation.

`NativeBootstrap` accepts only the supported BinaryPin and shorter bounded wall
deadline/cancellation. It accepts no prompt, auth/config directory, environment,
command, workspace, image or network choice. A held verified executable is copied
to a private temporary immutable mount source, hashed before/after each use, and
removed after exact container cleanup. It executes only safe-mode/restricted
version and help commands. Only bounded metadata hashes and expected controls
survive; raw output is not returned. An empty read-only workspace, copied binary
and trusted no-network launcher are its only binds.

A development attempt to bind the held host `/proc/PID/fd` source failed to start
the container (exit128); the same pinned binary worked with a conventional file
bind. Do not assert a confirmed root cause. The private verified snapshot avoids
depending on that descriptor bind path, without changing the owner's binary.
This copies a verified executable only; it does not inspect or copy credentials.

Default tests must label their synthetic native fixture separately from actual
OS containment. An explicit live metadata opt-in can test the actual installed
pin with no login, gateway, model or paid call. Version/help/bootstrap metadata
does not establish authenticated inference, native tool/MCP conformance, current
policy/grant/lease/budget authority, credential containment or G1/G2/G3. No existing
host pilot is silently switched or enabled. Connected auth/container integration
remains required.
