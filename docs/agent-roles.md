# Agent roles and instruction scope

## Engineering agent

The root `AGENTS.md` applies to repository engineering: building, integrating, and verifying the control plane. It links to the audit, implementation plan, progress log, and relevant system contracts. It does not initiate daily research or newsletter production.

## Future newsletter runtime

The newsletter workflow is product behavior, not the default engineering role. Its versioned operating specifications live in the [`crypto-daily` skill](../.agents/skills/crypto-daily/SKILL.md), its referenced evidence/editorial/release contracts, and the [edition contract](edition-contract.md). Consult them when implementing, reviewing, or explicitly operating the corresponding workflow. They do not authorize provider access, paid operations, trading, external messages, or publication; source policy and human approval boundaries remain in force.

No newsletter-runtime `AGENTS.md` is currently defined or activated. If one is introduced later, scope it only to an explicitly selected runtime workspace and preserve the root engineering boundary.

## Instruction discovery

Codex discovers applicable `AGENTS.md` files from the repository path to the working directory, so a nested instruction file has a narrower scope. The repository's `examples/synthetic-workspace/AGENTS.md` is a test fixture for discovery only; it contains no runtime newsletter policy or authorization. This repository does not use a nested runtime instruction file.
