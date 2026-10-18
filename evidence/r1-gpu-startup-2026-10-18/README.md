# R1 current-candidate qualification and GPU startup correction

The owner resumed R1 closure on 2026-10-18 and selected existing Claude
subscription plus local inference only. AOS-016-TC04 (paid SDK compatibility)
is deferred, not passed; no OpenAI API use is enabled by mentioning an existing
key. The original G1 manifest is preserved.

At clean main `9a7d5d547ace91486eca5b47c8719cf0181c9147`, three actual installed
Claude startup/proposal/registered-check tests passed. The fixed public fixtures
remain narrower than a complete R1 native worker certificate.

On the same source, the actual offline/hardware run had two passes and three
failures. All ten Ask answers met their content/scope assertions, but warm p95
TTFT was 14.9406 seconds against the existing 3-second requirement. The model
reported zero VRAM offload; the GPU pressure allocation returned CUDA error 999.
Separate read-only host and owned-container compute initialization also returned
999, despite successful NVML inventory. No driver reset/reload was attempted.
The failed original JUnit is unchanged and is not a release pass.

The correction rejects a requested GPU runtime before Docker enumeration,
orphan reclamation or create when bounded host compute initialization fails.
It does not change explicit CPU operation or relax latency/pressure assertions.
Forty related checks pass at the exact clean correction source in `report.json`;
Ruff, mypy (200 source files), all 11 import contracts and secret scan pass.
The report preserves original candidate and artifact hashes separately.

Remaining R1 work includes full native Build/hostile-profile conformance,
current-candidate cumulative acceptance evidence and the unresolved host GPU
qualification. This component does not complete G1 or the owner review.
