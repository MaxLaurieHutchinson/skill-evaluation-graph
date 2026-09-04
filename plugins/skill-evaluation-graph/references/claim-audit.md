# SEG Claim Audit & Technical Verification Matrix

This document defines the evidence level behind SEG's major capability claims. Public wording must not exceed the evidence recorded here.

## Evidence levels

1. **Implemented** — code or packaging exists, but no automated execution evidence is required.
2. **Unit Tested** — isolated tests use fixtures, synthetic inputs, or mocked/local dependencies.
3. **Integration Tested** — multiple SEG subsystems are exercised together.
4. **Live Host Tested** — executed directly against a real authenticated external host CLI.
5. **Benchmark Verified** — replicated live Control vs. Treatment trials demonstrate measured effect, including variance/uncertainty appropriate to the benchmark.

## Capability matrix

| Capability | Public wording | Evidence level | Evidence / limitation |
|:---|:---|:---:|:---|
| **Evaluation Graph** | Dependency-driven evaluator DAG with fail-closed execution integrity | **Integration Tested** | `src/seg/graph.py`, `src/seg/oracle.py`, graph/repair tests. Static thread timeout is a soft status boundary, not forced thread cancellation. |
| **Specification Conformance** | Authoritative external requirements are emitted as `SPECIFICATION_ERROR` findings and block `ACCEPT` | **Integration Tested** | Agent Skills rules plus configured host manifests. Codex rules cite the OpenAI plugin specification that owns the schema. |
| **Cross-Harness Packaging** | Validates configured Agent Skills, Claude Code, Gemini CLI, and Codex packaging evidence | **Unit Tested** | A valid manifest is packaging evidence only; it is not live-host verification. `gemini-extension.json` is a Gemini CLI extension manifest, not an Antigravity plugin manifest. |
| **Antigravity Compatibility** | SEG can be installed as an Agent Skill in Antigravity | **Implemented** | Antigravity supports Agent Skills in `.agents/skills/` and global skill locations. SEG does not claim a dedicated Antigravity Harness Adapter or native Antigravity plugin manifest. |
| **Codex Harness Adapter** | Isolated Codex Harness Adapter with minimal auth bridging | **Live Host Tested** | One authenticated live host execution has been performed. This proves executable integration, not statistically significant behavioural uplift. |
| **Behavioural Trial Runner** | Paired Control vs. Treatment trials, invalid-trial isolation, transcript/latency evidence | **Live Host Tested** | Runner and Codex Adapter executed on a live host. **Not Benchmark Verified** until replicated benchmark tasks demonstrate measured effect. |
| **Repair Verification** | Repair Candidates are evaluated in a sandbox and checked by the DAG + Oracle before authorized mutation | **Integration Tested** | Default read-only; mutation requires explicit authority; gate regression/new errors reject the candidate. |
| **Rollback-Protected Mutation** | Pre-mutation snapshot restores target on failed mutation | **Integration Tested** | This is rollback protection, not filesystem-atomic multi-file replacement. |
| **Tamper-Evident Receipts** | Deterministic SHA256 receipt and evaluated-tree digests | **Unit Tested** | Detects payload/tree changes within documented coverage. Not a digital signature, third-party attestation, or immutable storage system. |
| **Context & Token Economy** | Static token/context profiling using the SEG Context Tier Model | **Unit Tested** | Tier model and thresholds are SEG Recommendations unless an external specification explicitly owns a requirement. |
| **Privacy / Workstation Path Detection** | Detects common local workstation paths before publication | **Unit Tested** | Pattern-based detection is not a guarantee that all PII/secrets will be found. |
| **Destructive Command Guard** | Detects configured destructive command patterns and fails Safety where applicable | **Unit Tested** | Pattern-based guard over supported file types; not a general malware or shell-safety proof. |
| **Compaction Recovery Hooks** | Hook assets exist for supported host integration workflows | **Implemented** | No claim of compaction immunity. Host-specific live verification should be recorded separately when performed. |

## Authoritative sources

External requirements must cite the primary source that owns the rule.

- **Agent Skills** — `agentskills/agentskills` specification.
- **OpenAI Codex plugin / marketplace** — OpenAI `plugins` repository plugin JSON specification.
- **Google Gemini CLI extension** — Gemini CLI extension reference.
- **Google Antigravity Agent Skills** — Antigravity Skills documentation.
- **Anthropic Claude Code** — Anthropic Claude Code plugin documentation.

When a source changes, SEG's validator and its regression fixtures should be reviewed together.

## Terminology boundaries

Use these exact distinctions in public material:

- **Compaction Recovery**, not compaction immunity.
- **Tamper-Evident Receipt**, rather than language implying signatures or permanent storage guarantees.
- **Read-Only Default**, not autonomous silent mutation.
- **Rollback-Protected Mutation**, not atomic rollback.
- **Fail-Closed Integrity**, not best-effort checking.
- **Isolated Harness Configuration**, not hermetic benchmarking.
- **Soft Timeout Boundary** for static thread-backed Evaluators, not hard thread termination.
- **Live Host Tested** is not **Benchmark Verified**.
- **Packaging Evidence** is not **Target Verification**.

## Release rule

A public capability claim is allowed only when:

1. the implementation exists;
2. the stated evidence level is reproducible;
3. known limitations are preserved beside the claim where material;
4. externally governed rules cite their current primary source.

If any of those conditions stop being true, lower or remove the claim before release.
