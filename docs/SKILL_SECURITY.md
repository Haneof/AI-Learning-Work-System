# Skill Package Validation and Sandbox Harness

## Role in the product

The final goal is a vertical LoRA expert: a 4B base model plus a domain-specific adapter trained on double-verified knowledge packages. Skill packages and Docker isolation are validation machinery for training material and model behavior—not the destination product.

The validation harness must test that an expert can reason from a goal and current interface state, choose an appropriate action, verify the outcome, and recover safely. It must not reward blind replay of a single tutorial's exact coordinates or click sequence.

## Package format

Each validation skill is a versioned directory containing:

- manifest.json: id, version, goal, scope, inputs, outputs, tools, permissions, risk, evidence, tests, and optional dependencies.
- SKILL.md: human-readable knowledge and validation criteria.
- tests/: acceptance tests and fixtures.
- references/: source evidence and trusted references.
- scripts/: optional executable test helpers.

The validator computes a deterministic SHA-256 package hash over sorted relative file paths and file bytes. A skill version cannot be registered with a different package hash; content changes require a version increment.

## Static validation

The validator checks required fields, identifier and semantic-version formats, allowlisted tools and permissions, dependency allowlists, required test files, symlinks/path escapes, Python syntax, and selected dangerous imports/calls.

Static analysis is a screening layer, not a security boundary. It cannot prove arbitrary Python code safe and can be bypassed by obfuscated or dynamically constructed behavior.

## Isolated execution

DockerSandboxRunner revalidates the package immediately before execution and verifies that the supplied package hash still matches. It builds a Docker command with:

- network disabled;
- read-only container root filesystem and read-only package mount;
- dropped Linux capabilities and no-new-privileges;
- non-root UID;
- process, memory, CPU, and timeout limits;
- temporary no-exec /tmp and controlled output storage;
- immutable image digest and no image pull during execution;
- forced container removal if the host-side timeout expires.

The caller must use a trusted, locally preloaded image pinned by digest. Never mount the Docker socket, user home, cloud credentials, or other host secrets.

This is an isolation harness, not proof of production-grade security. Docker daemon configuration, kernel vulnerabilities, host filesystem exposure, Windows Docker Desktop behavior, and image provenance remain part of the threat model.

## Trained-expert validation

A LoRA adapter mounted on the 4B base must be evaluated through:

1. **Sandbox tests**: run bounded, deterministic tasks and verify inputs, outputs, permissions, and state assertions.
2. **GUI operation loop**: provide a goal and observe whether the expert identifies the current UI, chooses a valid action, verifies the resulting state, and adapts when the interface differs from the tutorial.
3. **Unseen variations**: test alternate routes, changed labels/layouts, unexpected dialogs, missing controls, and recovery scenarios.
4. **Safety checks**: reject unsupported actions, unauthorized side effects, and steps whose required evidence is absent.

A passing test is not just that an expected click occurred. The actual goal/result assertion must pass. Expert evaluation should record the base revision, LoRA adapter hash, test set, sandbox image, GUI trace, and report.

## Approval and training boundary

Only knowledge packages that pass GPT review and PM Sangou's independent video-evidence/test verification may enter the approved SQLite store and training dataset snapshot. The sandbox/compiler can validate those packages but cannot approve them. Training output is a versioned LoRA adapter; the validation harness does not replace the expert.
