# 0016: Self-hosted Release 1 scope, process model and migration policy

Status: proposed (2026-11-23) for owner confirmation in PR review. The scope choices
below were made by the owner on 2026-11-23. Accepting this record is the owner decision
that AGENTS.md requires before R7 distribution work is pulled ahead of the R3 gate.

## Context

A production-readiness review on 2026-11-23 found that the tree is a single-owner, loopback-only system.
The owner keeps its detailed record private until the security items it lists are fixed.

- Only R0/G0 has passed.
- The Codex adapter is absent and Delegate claim-support adjudication is absent.
- Packaging, setup, backup, upgrade, logging and release engineering are missing.

The phased plan delivers distribution in R7, after the R3 MVP and SOTA phases R4–R6.
The owner wants a production release that many users can install sooner.

## Decision

1. **Deployment model:** self-hosted per user. Each user installs and runs their own
   single-owner instance on their own Linux machine. A hosted multi-tenant service is
   out of scope. Its prerequisites are listed in the plan, not built.
2. **Release 1 (v1.0) scope:**
   - offline Ask with scoped memory;
   - one-worker Claude Build on the user's own repositories, under explicit grants per ADR 0011;
   - Mission Control views for these;
   - setup, doctor, service units, backup, restore and upgrade.

   **Release 2, behind feature flags that default to off:** Delegate research, the Codex
   adapter, two-worker plans, the phone companion, the background quota queue, encrypted
   profiles, the cloud SDK route, usage/cost/trace views and the multi-call tool loop.
3. **Platform:** Linux x86-64 only, with a published support matrix. Rootful Docker is
   supported, with a documented warning that the `docker` group is root-equivalent.
   Rootless Docker moves to Release 2.
4. **Process model** (consistent with RP 3.3 and ADR 0009). There are three `systemd --user` units:
   - an app server (API and UI) that never runs workflows;
   - a `panestria worker` process that owns durable Build workflows and model admission;
   - PostgreSQL.
5. **Migrations:** forward-only, with rollback by restoring a backup. Two consequences:
   - The product CLI exposes no downgrade.
   - Alembic downgrades refuse populated data.

   This takes the role RP 6.6c reserved for "ADR-0016". RP's upgrade/rollback item
   implements this record.
6. **Release gate:** a new `REL1` gate. It binds the relevant G1 cases plus production
   cases: wheel install, upgrade, backup drill, crash drills, adversarial suite and
   performance budgets. Release 1 also requires a 14-day owner trial, an external beta
   and an external security review. The flags-off configuration is the one gated and
   pentested.
7. **Governance:**
   - R1–R3 gates, owner acceptance and SOTA authorisation remain as defined for the MVP track.
   - This record authorises only the R7 distribution items named in the plan, pulled forward for Release 1.

## Consequences

- [The production-readiness plan](../docs/project/PRODUCTION-READINESS-PLAN.md) becomes
  the execution order for Release 1. It reuses the R3 remediation plan's items by ID.
- `docs/phase-tracker.json` gains Release-1 status after this record is accepted.
- Release-2 features stay in the tree but are unmounted and refused when their flag is off.
- **Open gate (plan item 0.5).** Automated per-user Claude Code subscription use must be
  confirmed as permitted before the containerised-CLI work starts. If it is not, Release-1
  Build needs the API-key route and this scope is revisited.
