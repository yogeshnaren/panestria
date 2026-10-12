# Attached Agent Skills v0.1.0 — source inventory and test evidence

**Inspected:** 2026-10-11. **Status:** source-attached, checksum-verified, synthetic smoke-tested; not installed or integrated into AgentOS. Instructions in SKILL.md files are reference data here and confer no authority. The original ZIP was preserved exactly, SHA256 `bf9178cbd7800852e0167452900659f5a8238eb71754aa3b7944117ef35ceba6`.

| Asset | Path inside ZIP | Planning integration |
|---|---|---|
| hardware-probe | agentos-skills/skills/hardware-probe/scripts/hwprobe.py | AOS-015; five presets present and independently smoke-checked |
| goal-contract | agentos-skills/skills/goal-contract/scripts/validate_contract.py | AOS-002; explicit legacy enum/envelope migration required |
| claude-code-worker | agentos-skills/skills/claude-code-worker/scripts/ | AOS-010; dry-run/config quarantine fixtures only |
| verified-research-brief | agentos-skills/skills/verified-research-brief/scripts/verify_citations.py | AOS-021; add retained source hashes/spans and scope enforcement |
| egress-preflight | agentos-skills/skills/egress-preflight/scripts/egress_manifest.py | AOS-008/012/029; descriptive manifest is not a network guard |
| milestone-handoff | agentos-skills/skills/milestone-handoff/scripts/check_features.py | AOS-025/027a/027b; evidence/tree linkage still needs integration |
| capture-learning | agentos-skills/skills/capture-learning/scripts/validate_candidates.py | AOS-011/012/036; replace used boolean with versioned five-stage events |

## Observed verification

- ZIP CRC test passed. All 29 supplied SHA256SUMS entries match. The supplied checksum list does not cover every later-added metadata file: the independent [full inventory](skills-file-inventory.json) hashes all files, including MANIFEST.md and SHA256SUMS. Package CHECKSUMS.sha256 also covers the attached ZIP and inventories.
- The original production ZIP's 52 checksum entries matched before editing; pristine input archives remain preserved in the delivery's originals folder.
- The supplied tools/test_skills.sh ran in a disposable copied fixture directory: **16 smoke assertions passed**, zero failures; **seven Agent Skills format validations were skipped** because the agentskills validator is not installed. No dependency was installed to fill this gap. The original manifest's 23/23 claim is historical, not the observed result here.
- Five presets (lite-16gb, omen-8gb, omen-12gb, omen-16gb, mac-studio-512) exited successfully, produced parseable JSON and marked simulated=true. This is a smoke check, not independent validation of the preset hardware claims, placement accuracy or throughput estimates. No real hardware probe, model pull, Ollama benchmark, vendor login or live worker launch ran.
- [Smoke transcript](skills-smoke-tests.txt), [hardware preset outputs](hardware-preset-tests.json), [supplied manifest](agentos-skills-v0.1.0.MANIFEST.md) and [supplied checksums](agentos-skills-v0.1.0.SHA256SUMS) are included.

## First planning slice

Verify the ZIP hash before extraction into a synthetic workspace; verify the supplied entries and independent inventory, then inventory skill frontmatter/scripts/dependencies/license provenance. Re-run the format validator at an explicitly pinned version and the supplied synthetic suite. Resolve missing license/permission manifests before redistributing/adopting code in a shipped product. Do not install skills, execute their install script, access credentials or start a live worker as a side effect of inventory. Adapt only the relevant source through a reviewed commit; preserve original ZIP/hash and record any new version.

Known migration work includes the [canonical acceptance guide](../architecture/04-ACCEPTANCE-CHECKS-AND-SKILL-MIGRATION.md), immutable source hashes/text positions for citations, five-stage memory usage, and current vendor version/security fixtures. Passing prototype smoke checks does not replace the AOS security and recovery gates.
