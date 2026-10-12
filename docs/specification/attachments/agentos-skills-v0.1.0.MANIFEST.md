# Manifest — agentos-skills v0.1.0

Built 2026-10-11. Seven Agent Skills plus the hardware probe (`skills/hardware-probe/scripts/hwprobe.py`).

## Verification at build time

- Official spec validator: `agentskills validate` (skills-ref 0.1.1) — all 7 skills valid
- `tools/test_skills.sh`: 23 of 23 checks passed (Python 3.13, Linux x86_64)
- Not yet run on the HP Omen; `run_worker.py` tested in --dry-run only (Claude Code not installed in the build environment)

Re-verify after unzipping: `pip install skills-ref pyyaml && tools/test_skills.sh`, and `sha256sum -c SHA256SUMS`.

## Files

```
./README.md
./skills/capture-learning/SKILL.md
./skills/capture-learning/assets/candidate.examples.jsonl
./skills/capture-learning/scripts/validate_candidates.py
./skills/claude-code-worker/SKILL.md
./skills/claude-code-worker/references/flag-profile.md
./skills/claude-code-worker/scripts/prepare_worktree.py
./skills/claude-code-worker/scripts/run_worker.py
./skills/egress-preflight/SKILL.md
./skills/egress-preflight/assets/egress-policy.example.json
./skills/egress-preflight/scripts/egress_manifest.py
./skills/goal-contract/SKILL.md
./skills/goal-contract/assets/goal-contract.template.yaml
./skills/goal-contract/scripts/validate_contract.py
./skills/hardware-probe/SKILL.md
./skills/hardware-probe/scripts/hwprobe.py
./skills/milestone-handoff/SKILL.md
./skills/milestone-handoff/assets/HANDOFF.template.md
./skills/milestone-handoff/assets/features.template.json
./skills/milestone-handoff/scripts/check_features.py
./skills/verified-research-brief/SKILL.md
./skills/verified-research-brief/assets/example/brief.md
./skills/verified-research-brief/assets/example/sources.json
./skills/verified-research-brief/assets/example/sources/S1.txt
./skills/verified-research-brief/assets/example/sources/S2.txt
./skills/verified-research-brief/references/format.md
./skills/verified-research-brief/scripts/verify_citations.py
./tools/install_skills.sh
./tools/test_skills.sh
```
