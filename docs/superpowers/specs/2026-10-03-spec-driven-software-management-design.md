# Spec-driven software management: high-level design

## Purpose and governing rule

The service manages a software solution through an authoritative, versioned Software Specification. The specification defines the intended system; generated source code and deployed components are replaceable outputs. Production data is durable state and must survive code regeneration. A clean rebuild from a selected specification revision is a required proof of completeness.

The service supports one solution made of any number of applications, frontends, services, libraries, data stores, and infrastructure components. Components may use different languages and toolchains. The specification defines their relationships rather than imposing a fixed application template.

## Core records and authority

| Record | Purpose | Authority |
| --- | --- | --- |
| Specification revision | Product behavior, constraints, component graph, data rules, and acceptance criteria | Authoritative desired state in Git |
| Resolved blueprint | Precise component designs, contracts, toolchains, dependencies, and generation inputs | Versioned part of the specification |
| Generated implementation | Source, packages, applications, and deployment definitions | Rebuildable output |
| Solution release manifest | Exact artifact digests, configuration references, spec revision, and compatibility evidence for one deployable system | Authoritative deployment selection |
| Production data | Actual business records and operational state | Durable external state, protected by spec-defined contracts and recovery rules |
| Evaluation record | Inputs, observed behavior, measurements, judgments, and reviewer decisions | Evidence linked to a candidate or release |

The specification and implementation should initially use separate Git repositories to make the authority boundary clear. The component graph may map generated components to one or more implementation repositories. Repository layout is a recorded design choice, not a restriction of the model. Secrets and external account credentials are referenced through controlled interfaces; their values are never generated into the specification.

## Layered specification

1. **Product intent:** users, goals, journeys, success measures, and use cases.
2. **Behavioral contracts:** interfaces, business rules, examples, accessibility requirements, and acceptance criteria.
3. **System design:** component graph, data ownership, trust boundaries, integration contracts, deployment boundaries, and quality requirements.
4. **Data specification:** models, invariants, schemas, retention, version compatibility, migration, backup, and recovery rules.
5. **Implementation blueprints:** component internals, algorithms where required, dependencies, toolchains, build inputs, and generation settings.
6. **Verification and operations:** tests, workloads, performance targets, observability, release policy, experiments, and recovery drills.

Every requirement and component has a stable identifier. References connect use cases to contracts, components, tests, releases, and observed failures. The specification records assumptions explicitly, including expected load and data growth when users have not supplied exact values.

Exploration may yield several candidate blueprints or implementations. Once a blueprint, generator version, toolchain, and dependencies are pinned, code generation should be reproducible from those inputs. A better candidate becomes durable only when its winning design decisions, tests, or constraints are incorporated into the appropriate specification layer.

## Dependency and compatibility graph

The graph includes applications, frontend experiences, services, libraries, schemas, contracts, data stores, and infrastructure. Each node declares responsibility, interfaces, dependencies, ownership, version, build rules, and verification. Edges record both build dependencies and runtime compatibility requirements.

Change analysis operates in both directions. A feature in a top-level application may require a new foundation-library or service capability. A library, schema, or service change propagates to all dependent components. The reconciler computes the complete affected set, detects compatibility breaks, and produces a change set with corresponding tests. Affected components may be regenerated selectively, but a clean full-system rebuild remains a standing validation exercise.

Components can have independent versions and release schedules when compatibility rules permit. A breaking change creates a coordinated release group. An environment deploys only an evaluated solution release manifest, never an arbitrary mix of component versions.

## Service architecture

| Unit | Responsibility |
| --- | --- |
| Intake and issue service | Capture feature requests, defects, findings, test inputs, and runtime observations; link them to spec identifiers |
| Spec workspace | Manage proposals, branches, reviews, stable references, validation, and candidate blueprints |
| Reconciliation controller | Watch spec revisions and implementation drift; calculate affected components; schedule generation and verification |
| Specialist workbench | Invoke product, architecture, engineering, security, infrastructure, data, QA, and documentation capabilities as needed |
| Build and evaluation service | Build candidate stacks, run automated checks, exercise APIs and UIs, and collect comparable evidence |
| Release controller | Produce and promote cohesive manifests under versioned approval policies |
| Experiment controller | Allocate production traffic to complete, compatible variants and measure outcomes |
| Observability and recovery service | Correlate telemetry with revisions, diagnose bottlenecks, rehearse restores, and open corrective issues |
| Bootstrap supervisor | Start a known-good controller, retain release history, and recover the management service when its own generated implementation fails |

These are logical boundaries. The first implementation may combine several in one process while keeping their interfaces separate.

## Change and reconciliation workflow

1. Intake creates an issue or feature proposal with a stated outcome and available test inputs.
2. Relevant specialists analyze impact and propose spec changes on a branch. Spec commits trigger candidate generation promptly, including on proposal branches.
3. The reconciler resolves dependencies, generates one or more implementation candidates, and opens linked code PRs. Each candidate records its exact spec revision and generation inputs.
4. Each candidate is built as a complete preview system. The evaluation service runs submitted and spec-derived service tests, and applicable UI tasks using computer-use-capable evaluation. It records observed outputs and uncertainty rather than silently treating model judgments as facts.
5. A human reviews the running candidate and evaluation evidence. Code review is available. Revisions return to the spec or blueprint and trigger another generation cycle.
6. The selected spec revision and implementation artifacts are recorded in a solution release manifest. The spec becomes accepted desired state; the release controller promotes the tested manifest under the applicable policy.
7. The controller checks for drift and failed convergence. Direct code fixes that should survive regeneration are represented in the spec before being treated as lasting solutions.

An issue may reveal that the code violates a correct spec or that the spec itself is incomplete. Both paths remain explicit. A rejected candidate does not become the accepted release.

## Data integrity and recovery

Data integrity is a promotion gate. The data specification defines ownership, contracts, invariants, schema evolution, retention, and recovery targets per dataset. It also defines how applications and services behave during migrations and rollbacks.

Every data-changing release includes a migration plan, compatibility window, validation checks, and a recovery procedure. Migrations are rehearsed against representative data before production promotion. Destructive changes require an explicit plan for data already written by the new version; reverting code alone is insufficient. The platform validates backups through restore drills and records the results. Recovery objectives and acceptable loss are explicit rather than inferred from the presence of backups.

Production experiments with breaking data models require compatible shared-data semantics or isolated data paths and a defined reconciliation procedure. An experiment cannot bypass data integrity gates.

## Release and production experimentation

A release manifest pins the full system: artifact digests, compatible component versions, spec revision, configuration references, migration state, and verification evidence. Deployment promotes this evaluated set. A distributed rollout may require parallel stacks, staged traffic switching, or a coordinated maintenance window; the platform records the transition method and does not assume atomic changes across independent services.

Promotion policies support both human approval of each step and automatic progression within explicitly preapproved limits. Policies are versioned and may vary by environment, application, experiment, and change risk. They define required evidence, exposure ceilings, health thresholds, stop conditions, and recovery actions. Production defaults to manual promotion until an authorized policy permits automation.

Production A/B experiments are specified changes. An experiment defines eligible users or tenants, assignment rules, variants, measures, guardrails, and completion criteria. Each arm points to a cohesive release manifest. Assignment remains stable across frontend and service requests. Component-level variants are permitted only when compatibility is demonstrated; breaking variants use complete isolated stacks where necessary. Results and human judgments feed winning design choices back into the specification.

## Evaluation, scalability, and observability

The specification includes functional, security, accessibility, performance, scalability, and cost criteria. Evaluation uses explicit expected results where supplied and spec-derived expectations otherwise; uncertain or subjective outcomes are presented to human reviewers. Candidate comparisons retain their inputs and test conditions.

Request telemetry connects frontend, middle services, backend, data access, and external or model calls. It is attributable to component, release manifest, spec revision, and experiment arm. Measures include interaction and request latency, throughput, concurrency, queue time, errors, resource saturation, token input and output, model-call latency, retries, and cost. Traces and profiles support bottleneck diagnosis across layers.

Scalability is a default quality concern. The spec records the intended operating range for users, requests, concurrency, and data volume, plus growth assumptions. Load evaluations produce capacity curves, tail latency, headroom, and cost per unit of work. A limit discovered in production creates an issue and a spec change affecting the bottleneck and any dependent components.

The management service itself reports generation time, evaluation time, queue depth, reconciliation failures, candidate cost, and recovery-test results.

## Self-hosting bootstrap

The management service is its first managed solution. Its own specification uses the same layers, component graph, data contracts, evaluation rules, and release manifests as other solutions. Self-hosting does not grant the running controller authority to replace itself without evaluation or promotion.

The bootstrap proceeds in stages:

1. **Seed:** hand-author the initial specification and build the smallest inspectable controller needed to read it, validate it, coordinate Git branches, invoke generation and builds, and record results. Keep a bootstrap supervisor and a known-good release outside the controller process so recovery does not depend on the failing version.
2. **Dogfood:** use the seed controller to manage issues and spec changes for the management service itself. Generate a successor on a branch and build it in an isolated environment while the seed continues serving users and preserving workflow state.
3. **Prove:** test the successor with the same submitted service and UI inputs used for other solutions. Rehearse state migration and recovery, compare observability and capacity, then perform a clean reconstruction from its own spec, pinned tools, and external durable state.
4. **Promote:** after the configured human or policy approval, publish a complete release manifest and switch the management service to the successor. Retain the prior controller and compatible state for recovery. The new version takes over future reconciliations only after health and data checks pass.
5. **Repeat:** subsequent changes follow the ordinary spec-to-candidate workflow. The controller can propose improvements to its own spec, but the spec review, evaluation, data integrity, and promotion rules still apply.

The bootstrap supervisor has a deliberately narrow role: start a pinned controller release, report health, switch between approved releases, and restore access to durable workflow state. Its own source and recovery artifact are retained independently so it can be reconstructed and operated when the generated management service is unavailable. A failure of the active controller must not erase the specification, release manifests, evaluation history, or production data. The initial seed can be retired only after a self-generated successor has passed a full rebuild and recovery drill.

## Representative use cases

- **New solution:** establish product intent and system contracts; explore architectures; select a blueprint; generate, evaluate, review, and release a complete implementation.
- **Feature:** update an application journey; trace required changes down to services and libraries; regenerate and evaluate the affected release group.
- **Defect:** reproduce with submitted inputs; determine whether spec or implementation is wrong; update the authoritative layer and verify a regression test.
- **Dependency or schema change:** trace effects upward to dependent applications; coordinate a compatible release and data migration.
- **Performance issue:** locate the limiting layer from telemetry; compare candidate optimizations under comparable load; capture the chosen design in the spec.
- **Production experiment:** run two cohesive releases for eligible users; compare outcomes and guardrails; promote the selected design through a spec change.
- **Disaster recovery:** recreate generated code and deployable components from a spec revision and restore durable data under its recovery rules.
- **Rollback:** select a known-good release manifest and execute its data-aware recovery plan; reconcile the spec if the desired state is changing.
- **Self-upgrade:** revise the management service's own spec; generate and evaluate its successor beside the active controller; promote a tested release while preserving a known-good recovery path.

## Delivery sequence

1. Define the management service's own spec format, stable identifiers, component graph, compatibility rules, data contracts, and validation.
2. Build the seed controller and independent bootstrap supervisor; exercise one complete self-change through spec commit, generation, preview, submitted tests, human review, and a cohesive release manifest.
3. Generate and promote the first successor of the management service; prove that a clean rebuild and recovery work while preserving its durable state.
4. Add data migration rehearsals, drift detection, multiple languages, libraries, applications, selective regeneration, and independent compatible releases.
5. Add candidate comparisons, performance and capacity analysis, and policy-controlled production A/B experimentation.

The first slice should include the management service's own frontend, service, library, and persistent workflow data so the central claims can be tested rather than assumed. A second small target solution can expose assumptions that self-hosting alone does not reveal.
