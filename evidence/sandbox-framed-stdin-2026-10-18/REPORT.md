# Bounded sandbox stdin transport observation

**PASS_COMPONENT**, source `c1963e29a2577e14b71f6aa9aad0303abacf930b`, clean.

211 focused checks pass in75.40s; 20 existing live cases are excluded. There are
38 new cases: 21 contract/real OS-pipe checks, 16 actual Docker resource cases and
one actual PostgreSQL authority check. Ruff/mypy198/11 imports/secret/diff pass.
No provider, model, vendor CLI, SDK, credential or owner-service work is involved.

Raw development31/32, actual admission1, clean earlier206, attach13, output15,
clean earlier210 and final211 results remain separate and byte-exact. Review
after earlier passes added partial-registration cleanup, actual attachment/exit
checks and required captured output. These are new validations, not relabeled
earlier passes. `report.json` binds their source states and hashes.

Actual container configuration, EOF/digests, seccomp/socket denial, pressure,
cancellation, client death and exact cleanup are asserted. Two client-failure
cases inject a program into an otherwise actual created-container lifecycle.
OS-pipe cases substitute the container-state seam. Existing direct-runner SIGKILL
regressions do not become actual gateway crash evidence.

The production gateway still stages host inputs. This transport has no native
task certificate or release authority. Digests/consumption require the trusted
consumer; dispatch admission, gateway execution semantics and stage removal must
be integrated separately. Full G1/G2/G3 and the owner trial remain incomplete.
