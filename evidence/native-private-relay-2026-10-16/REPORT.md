# Native private relay transport evidence

Clean source `c6fa58982650fd48c1d9e6907655cba6fd1c5952` passes 74 focused default checks and one explicitly opted-in actual public TLS HEAD. Ruff, mypy (190 files), 11 import contracts and secret scan pass. The report pins source and original JUnit hashes; earlier development and clean-source timing failures remain separate observations.

Four actual Docker tests verify the network-disabled, nonroot, read-only resource/mount envelope, synthetic host-sentinel/environment separation, actual host-loopback/direct TEST-NET denial, forbidden CONNECT, replaced socket refusal and owned shutdown. Large socket transfer, half-close, backpressure and byte/connection/deadline limits are exercised. The wrong-peer UID unit case uses injection and is not claimed as a different-UID OS probe.

The live test verifies CA/hostname-checked TLS through the container loopback proxy, pinned private Unix socket and host gateway to `api.anthropic.com`. It sends one unauthenticated HEAD, no model request, credential, private content or paid SDK call.

This transport does not launch or certify a native CLI/auth process, authorize a task/connection, inspect encrypted application content, prevent generic domain fronting, or complete AOS-008/AOS-010/G1/G2/G3. A trusted pinned client must enforce TLS/SNI/application behavior. Native container/profile/auth/MCP integration, current policy/grants/lease/budgets, revocation and full conformance remain required. No owner checkout, DB or service changed.
