# Skill Package Validation and Sandbox PoC

## Package format

Each skill is a versioned directory containing:

- manifest.json: id, version, goal, scope, inputs, outputs, tools, permissions, risk, evidence, tests, and optional dependencies.
- SKILL.md: human-readable operating instructions.
- tests/: acceptance tests and fixtures.
- references/: trusted reference material.
- scripts/: optional executable scripts.

The validator computes a deterministic SHA-256 package hash over sorted relative file paths and file bytes. A skill version cannot be registered with a different package hash; content changes require a version increment.

## Static validation

The validator checks required fields, identifier and semantic-version formats, allowlisted tools and permissions, dependency allowlists, required SKILL.md, symlinks/path escapes, Python syntax, and selected dangerous imports/calls.

Static analysis is a screening layer, not a security boundary. It cannot prove arbitrary Python code safe and can be bypassed by obfuscated or dynamically constructed behavior.

## Isolated execution PoC

DockerSandboxRunner builds a Docker command with:

- network disabled
- read-only container root filesystem
- package mounted read-only
- dropped Linux capabilities and no-new-privileges
- non-root UID
- process, memory, CPU, and timeout limits
- temporary no-exec /tmp filesystem
- immutable image digest and no image pull during execution

The runner revalidates the package immediately before execution and verifies that the supplied package hash still matches. It also uses a trusted, locally preloaded image pinned by digest. Never mount the Docker socket, user home, cloud credentials, or other host secrets.

This is not production-grade isolation. Docker daemon configuration, kernel vulnerabilities, host filesystem exposure, Windows Docker Desktop behavior, and image provenance remain part of the threat model. The PoC tests command construction; they do not execute hostile code.

## Approval boundary

The current allowlist only permits workspace read/write and pure local parsing/extraction tools. Network access, shell tools, arbitrary dependencies, and L3 external side effects are denied. Payment, publishing, deletion, account authorization, and other external actions must be represented as human approval requests and are not executed by this PoC.
