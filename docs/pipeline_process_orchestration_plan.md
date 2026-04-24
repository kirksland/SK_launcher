# Pipeline Process Orchestration Plan

Date: 2026-04-23

This document captures the design direction for turning the launcher into a real production orchestration layer for Houdini/USD workflows, instead of a simple browser/launcher utility.

The goal is to support structured process execution across modeling, rigging, animation, groom, FX, CFX, lookdev, layout, lighting, rendering, and downstream review workflows, while keeping the architecture modular and scalable.

This document intentionally focuses on structure, contracts, and execution flow. It is not a script wishlist.

## Vision

The launcher should evolve toward a production cockpit for procedural pipelines.

That means the app should eventually be able to:

- understand production context
- understand published data and dependencies
- detect stale downstream setups after upstream changes
- propose or execute rebuild/update processes
- expose process state, history, and validation clearly
- launch deterministic Houdini/USD pipeline actions from a controlled framework

In practice, the launcher should sit between:

- project structure
- published pipeline data
- Houdini contexts
- USD scene assembly
- artist-facing review and validation tools

## Core Principle

We should not build this as a collection of special-case scripts.

The system must be built around:

- explicit entities
- explicit process definitions
- explicit dependency graph rules
- explicit execution contracts
- explicit status and validation rules

If a process exists, the launcher should know:

- what it consumes
- what it produces
- how to validate readiness
- how to report success/failure
- what downstream data becomes stale when outputs change

## Why This Matters

A modern Houdini/USD pipeline often has rebuildable or refreshable relationships like:

- model source -> rig build
- rig build -> animation setup
- model surface -> groom attachment
- asset publish -> shot assembly
- shot assembly -> lighting/render scene
- render outputs -> review media

The launcher should eventually become the place where these relationships are visible, actionable, and safe to update.

## Target Use Case

Example:

- an artist updates a procedural modeling source
- the change affects a character arm length
- the rig depends on guide curves or kinefx structure derived from that source
- animation, groom, USD asset publish, and downstream shots may now be out of date

The launcher should be able to represent this as:

```text
Source changed:
- characterA/model/source/arm_guides

Potentially impacted:
- characterA/rig/main
- characterA/anim/apex_setup
- characterA/groom/body
- characterA/usd/asset
- shots consuming characterA publish
```

Then the app should be able to:

- mark those dependencies as stale or needing review
- propose refresh actions
- optionally execute rebuild processes
- track process logs and results

## Design Constraints

This system must avoid:

- giant controller scripts
- direct UI-to-script coupling
- fragile path heuristics as the only source of truth
- hidden side effects
- magical process buttons with no declared contract
- per-process one-off implementations spread across the app

This system should prefer:

- typed entities and process definitions
- pure planning/data layers where possible
- domain services over widget-driven logic
- explicit execution records
- reusable execution infrastructure
- testable contracts

## High-Level Architecture

The target structure should look roughly like this:

```text
core/
  pipeline/
    entities/
      models.py
      context.py
      publish.py
      dependency.py

    graph/
      rules.py
      resolver.py
      impact.py
      stale.py

    processes/
      definitions.py
      registry.py
      validation.py
      planning.py

    jobs/
      models.py
      runtime.py
      queue.py
      logs.py

    execution/
      houdini.py
      usd.py
      local.py

controllers/
  process_controller.py

ui/
  pages/
    process_page.py
  widgets/
    process_run_panel.py
    dependency_status_panel.py
    stale_impact_panel.py
```

This is a target, not an instruction to build everything immediately.

## Foundational Concepts

### 1. Entity

An entity is a stable production object the launcher can reason about.

Examples:

- project
- asset
- shot
- task
- publish
- source data set
- cache
- USD assembly
- render output

An entity must not just be "a file path". A path may be attached to it, but the entity must have a stable identity and type.

### 2. Process Definition

A process is a formal production action, not a loose script.

Examples:

- build_rig_from_guides
- rebuild_groom_from_scalp
- update_anim_setup_from_rig
- publish_asset_usd
- refresh_shot_assembly
- export_review_media

A process definition should declare:

- id
- label
- domain
- supported entity types
- required inputs
- optional inputs
- produced outputs
- validation rules
- execution backend
- downstream invalidation rules

### 3. Job

A job is a concrete execution of a process.

A job should record:

- process id
- target entity/context
- parameters
- execution time
- current status
- logs
- result payload
- produced outputs
- failure reason if any

### 4. Dependency

A dependency should represent an explicit production relationship.

Examples:

- rig depends on model guides
- animation setup depends on rig publish
- groom depends on model surface
- shot assembly depends on asset publish
- lighting depends on shot assembly

Dependencies should be queryable, not implied only by naming convention.

### 5. Stale State

The system should be able to classify downstream objects as:

- up_to_date
- stale
- needs_review
- invalid
- missing_dependency

This state should come from explicit rules, not vague UI guesses.

## Execution Model

The target execution flow should be:

```text
UI intent
  -> process request
  -> process planner
  -> readiness validation
  -> job creation
  -> backend execution
  -> output registration
  -> dependency impact update
  -> UI refresh
```

Important rule:

The UI should request a process.
The process layer should decide whether the process is valid and executable.

## Recommended Phased Plan

### Phase 1. Vocabulary and Data Model

Goal:

Create the language of the system before trying to automate anything.

Work:

- define core entity types
- define process definition schema
- define job model
- define dependency model
- define stale state vocabulary
- document the minimal contracts

Deliverables:

- `core/pipeline/entities/models.py`
- `core/pipeline/processes/definitions.py`
- `core/pipeline/jobs/models.py`
- tests for model validation
- design doc updates

### Phase 2. Read-Only Dependency Graph

Goal:

Make relationships visible before making them executable.

Work:

- create a graph/resolver layer
- represent upstream/downstream links
- support impact analysis queries
- support stale detection rules without running processes yet

Example queries:

- what depends on this publish?
- what becomes stale if this source changes?
- what shots consume this asset?

Deliverables:

- `core/pipeline/graph/resolver.py`
- `core/pipeline/graph/impact.py`
- `core/pipeline/graph/stale.py`
- tests for dependency traversal

### Phase 3. Process Registry and Planning

Goal:

Describe processes in a stable, extensible way before wiring execution.

Work:

- add a process registry
- register a few real process definitions
- introduce process planning and readiness checks
- add validation messages that are readable in the UI

Candidate first processes:

- `publish_asset_usd`
- `refresh_shot_assembly`
- `export_review_media`
- `build_rig_from_guides` (only if the build is already deterministic enough)

Deliverables:

- `core/pipeline/processes/registry.py`
- `core/pipeline/processes/validation.py`
- `core/pipeline/processes/planning.py`
- tests for process selection and validation

### Phase 4. Job Runtime

Goal:

Run formalized processes through a shared execution runtime.

Work:

- create a local job runtime
- support logs, status, cancellation, and result collection
- ensure jobs do not update UI directly
- store execution records in a queryable form

Deliverables:

- `core/pipeline/jobs/runtime.py`
- `core/pipeline/jobs/logs.py`
- `controllers/process_controller.py`
- tests for job lifecycle

### Phase 5. Houdini/USD Backend Integration

Goal:

Bridge the formal process system to actual Houdini/USD tasks.

Work:

- add a Houdini execution backend
- standardize environment/bootstrap rules
- support parameterized process launches
- standardize result payload reporting

Important:

This should not start as arbitrary Python script execution.
It should start as constrained execution of registered process definitions.

Deliverables:

- `core/pipeline/execution/houdini.py`
- `core/pipeline/execution/usd.py`
- example process launchers
- validation tests around process invocation

### Phase 6. UI for Impact and Execution

Goal:

Expose the system to artists and TDs in a controlled, readable way.

Work:

- add process execution panels
- add impact/stale status panels
- display recommended refresh actions
- display job history and logs

The UI should support:

- inspect impact
- run process
- review failures
- review stale downstream items

Deliverables:

- process UI widgets/pages
- controller integration
- no business logic hidden inside widgets

### Phase 7. Controlled Automation

Goal:

Add optional automation only after contracts and visibility are solid.

Work:

- auto-mark downstream entities stale after publish
- auto-suggest refresh chains
- optionally auto-run safe deterministic processes
- keep human review gates for sensitive downstream updates

Examples of safer automation:

- regenerate thumbnails/previews
- rebuild deterministic USD assembly
- refresh caches with fully declared inputs

Examples requiring review:

- anything that may invalidate animation choices
- anything that changes groom behavior
- anything with ambiguous dependency mapping

## First Practical Slice

To avoid overbuilding too early, the first serious implementation slice should be modest.

Recommended first slice:

1. Define process and dependency models
2. Add read-only impact analysis
3. Show stale status in UI for a few entity types
4. Register one or two safe processes
5. Run them through a shared job runtime

This would let us prove the architecture before spreading it across every department workflow.

## Initial Candidate Domains

The first real domains worth supporting are probably:

- asset USD publish
- shot assembly refresh
- review/export generation
- deterministic rig rebuilds, only where data contracts are already strong

Animation, groom, and CFX are excellent targets, but they should come after we prove the dependency/process model.

## Anti-Monolith Guardrails

To prevent the system from collapsing into hard-to-maintain scripts, we should enforce the following rules:

### Rule 1

No UI widget launches a raw script directly.

### Rule 2

Every executable action must map to a registered process definition.

### Rule 3

Every process must declare inputs, outputs, and validation rules.

### Rule 4

Dependency and stale logic must live in core pipeline services, not in page/controller glue.

### Rule 5

Job execution, logs, and results must pass through shared runtime infrastructure.

### Rule 6

Process-specific Houdini logic should live behind backend adapters, not leak into generic controllers.

## What Success Looks Like

This system will be on the right track when:

- upstream/downstream relationships are explicit
- stale status is understandable
- process execution is formalized and logged
- safe rebuilds can be launched from the app
- new processes can be added without growing one central giant controller
- artists can see what changed, what is impacted, and what to do next

## Proposed Branch Name

Recommended branch name:

```text
feature/pipeline-process-orchestration
```

Shorter alternative:

```text
feature/pipeline-orchestration
```

## Next Step

The next concrete step should be:

- create the Phase 1 data models
- add a minimal read-only dependency/impact prototype
- avoid any direct Houdini execution until those contracts exist

That gives us a serious architectural foundation without rushing into brittle implementation.

## Integration With The Current App

This section maps the orchestration plan to the current Skyforge application structure, so implementation can grow from what already exists instead of starting from an abstract greenfield design.

The launcher already contains several strong foundations:

- a multi-page application with clear domain entry points
- a global command/shortcut system
- a board architecture that was recently cleaned and modularized
- an asset manager that already understands project/entity navigation
- settings and startup/runtime infrastructure
- local Windows build/distribution flow

That means the orchestration system should be introduced as a new domain layer inside the existing app, not as a separate parallel app living beside it.

## What We Already Have That Helps

### 1. Domain-Oriented UI Structure

The application already has pages and controllers for major domains:

- projects
- asset manager
- board
- client sync
- settings

This is useful because orchestration should become another cross-domain service layer that these existing pages can query, not a replacement for them.

In practice:

- the asset manager can surface dependency and stale status
- the board can consume process results or review artifacts
- project context can define execution scope
- settings can expose process runtime preferences later

### 2. Existing Command System

The app now has a global command/shortcut architecture.

This is important because orchestration actions should not bypass that system.

Eventually, actions like:

- `process.run`
- `process.inspect_impact`
- `process.retry_last_failed`
- `process.show_downstream_status`

should be modeled as commands in the same command ecosystem, rather than custom button logic that calls random scripts directly.

### 3. Board Refactor Lessons

The board refactor already taught the right structural lesson:

- keep the page as a composition root
- move behavior into focused controllers/services
- drive extensibility through contracts and metadata
- remove legacy compatibility when it no longer matches the target architecture

The orchestration system should follow the same rule set.

That means:

- no giant `process_controller.py` doing everything
- no process-specific UI logic hidden in pages
- no direct widget-to-backend coupling
- process definitions and dependency logic should live in core domain code first

### 4. Asset Manager As The Natural First Consumer

The asset manager is probably the best first integration point.

It already understands:

- project roots
- assets
- shots
- library entities
- versions
- previews
- inventory browsing

That makes it the right place to start showing:

- stale status
- upstream/downstream relationships
- available processes for the selected entity
- impact summaries

In other words, the asset manager can become the first orchestration-aware UI without needing a full dedicated process page immediately.

## Proposed Placement In The Current Codebase

The safest approach is to add a new vertical slice under `core/` and a thin controller layer under `controllers/`.

### Core Layer

Proposed new package:

```text
core/pipeline/
```

This should be the source of truth for orchestration concepts.

Recommended first structure:

```text
core/pipeline/
  entities/
    models.py
    context.py

  processes/
    definitions.py
    registry.py
    validation.py

  graph/
    models.py
    resolver.py
    impact.py
    stale.py

  jobs/
    models.py
    runtime.py
```

Why here:

- this is domain logic, not UI
- it needs to be reused by multiple pages/controllers
- it should be testable without Qt widgets

### Controller Layer

Recommended controller entry point:

```text
controllers/process_controller.py
```

This controller should not contain the business rules themselves.
It should act as a bridge between:

- UI pages/widgets
- current project/entity selection
- `core.pipeline.*` services

Its responsibilities should stay narrow:

- inspect selected context
- ask the pipeline graph for impacts/stale status
- ask the process registry which actions are available
- request job execution through the runtime
- relay logs/status/results back to the UI

If orchestration grows significantly, that controller can later be split into:

```text
controllers/process/
  controller.py
  impact_controller.py
  execution_controller.py
```

but we do not need to start there immediately.

### UI Layer

The first UI integration should probably not be a brand new giant page.

Instead, we should extend existing surfaces carefully:

- asset manager inspector
- asset manager version/inventory panels
- possibly a later dedicated process/jobs page

Recommended early widgets:

```text
ui/widgets/
  process_impact_panel.py
  process_actions_panel.py
  job_status_panel.py
```

These widgets should remain passive:

- display status
- emit signals
- let controllers ask core services what to do

## How To Connect It To Existing Domains

### Projects Page

The projects page should mostly remain a context selector.

Its orchestration role should be minimal:

- define active project root
- maybe expose project-wide health later

It should not become the main place where process logic lives.

### Asset Manager

This should be the first serious orchestration-aware area.

For a selected asset/shot/library entity, it should eventually show:

- current publish/dependency summary
- stale downstream summary
- available registered processes
- recent jobs for this entity
- recommended refresh actions

This gives users immediate value without requiring a full scheduler UI first.

### Board

The board should not become the orchestration center.

Its role is different:

- review
- visual comparison
- notes/feedback
- media-level interaction

However, later it can consume orchestration outputs:

- review renders
- compare before/after process results
- display media produced by jobs

So the board should remain a consumer of process outputs, not the place that owns dependency logic.

### Settings

Settings should eventually carry orchestration runtime configuration, such as:

- Houdini executable/runtime profiles
- local process worker limits
- log retention behavior
- temp/cache policy
- default execution mode

But this should come after the process model is stable.

### Client/Sync

This domain may later interact with orchestration through:

- syncing published outputs
- syncing review media
- syncing process artifacts

But it should stay downstream of the orchestration layer, not define process logic itself.

### Client/Server

The current client/server area should not be treated as a side feature. It can become an important part of the orchestration system.

In a stronger long-term design, the launcher may eventually need to support more than local process execution:

- local artist-side execution
- delegated execution on another workstation
- execution triggered from a shared server-side context
- sync of process outputs between environments
- inspection of remote process state

That means the existing client/server panel can evolve into part of the orchestration surface, especially for distributed or semi-distributed workflows.

Examples:

- launch a rebuild locally on the current workstation
- send a deterministic export/publish process to a designated machine
- inspect whether a downstream process was completed elsewhere
- sync published outputs or review artifacts after a job finishes
- compare local state versus server-side available outputs

This is especially relevant in a production environment where:

- artists may not all work on the same machine setup
- some processes are expensive and better handled elsewhere
- some outputs should be generated once and then shared
- local workstations should not become the only execution authority

## Extending The Architecture For Distributed Execution

If we include the client/server domain in the orchestration plan, the architecture should leave room for multiple execution targets.

The job runtime should not assume "run locally" is the only mode.

Instead, the target model should eventually look more like:

```text
process request
  -> planning
  -> execution target selection
  -> local runtime OR remote/runtime adapter
  -> job status/log/result collection
```

That implies a slightly broader target structure:

```text
core/pipeline/
  jobs/
    models.py
    runtime.py
    queue.py
    targets.py

  execution/
    local.py
    houdini.py
    usd.py
    remote.py
```

And possibly later:

```text
core/client_runtime/
  transport.py
  sync.py
  remote_jobs.py
```

The exact split can evolve, but the design requirement is clear:

The orchestration model should support the idea that a process may run:

- here
- elsewhere
- or through a shared execution authority

without changing the process definition itself.

## Revised Role Of The Client/Server Area

So the client/server area should eventually have two responsibilities:

### 1. Environment and Sync Responsibility

This is close to what it already does:

- identify clients/workstations
- show sync state
- compare local and server-side data
- push/pull needed project content

### 2. Orchestration Responsibility

This is the missing future layer:

- display remote execution targets
- show process/job availability per environment
- allow execution target selection
- inspect remote job status/logs
- fetch or sync outputs produced remotely

This does not mean the client/server page should own process definitions.

It means it can become the operational bridge between:

- pipeline process orchestration
- distributed execution
- content synchronization

## Concrete Integration Strategy

To integrate this cleanly into the existing app, we should think in terms of three layers:

### Layer 1. Process Definition Layer

Lives in:

```text
core/pipeline/processes/*
```

This layer defines what a process is.
It must remain independent from whether the process runs locally or remotely.

### Layer 2. Execution Target Layer

Lives in:

```text
core/pipeline/jobs/targets.py
core/pipeline/execution/*
```

This layer decides where and how the process runs.

Potential target examples:

- local workstation
- designated client machine
- central pipeline host

### Layer 3. UI/Operations Layer

Lives across:

- asset manager inspector for entity-centric process actions
- client/server area for execution target and sync state
- possible later jobs/process page for cross-project process monitoring

This split matters because otherwise the client/server page becomes a dumping ground for unrelated logic.

## Practical Example

Imagine the user is working on a character asset and the launcher detects:

- model source changed
- rig publish stale
- groom setup possibly stale
- USD asset publish stale

From the asset manager, the user might see:

- `Available actions`
- `Impacted downstream data`
- `Run refresh`

But once they choose `Run refresh`, the app could offer:

```text
Execution target:
- Local workstation
- Client machine A
- Pipeline host
```

Then the client/server side of the application would handle:

- whether that target is reachable
- whether it has the right environment
- whether outputs need syncing back
- how logs or artifacts are retrieved

That is a much stronger use of the existing client/server area than using it only as a sync helper.

## Implication For The Implementation Order

The previous phased plan still holds, but we should adjust our thinking:

- Phase 1 to Phase 3 can stay mostly local and read-only
- by Phase 4, job/runtime models should already include the concept of execution target
- by Phase 5, backend adapters should support at least the architecture for local vs remote execution, even if only local is implemented first

So even if we only implement local execution first, the models should already leave space for:

- target id
- target kind
- target status
- remote/local capability flags

That is the clean way to prepare the system without overbuilding.

## Updated Organization Rule

With the client/server domain included, the architectural rule becomes:

> Put process and dependency intelligence in `core/pipeline`, treat execution location as a separate runtime concern, and use the client/server area as the operational bridge for distributed execution and sync.

This is the version that looks farther ahead and fits the broader production system more honestly.

## Execution Targets And Capabilities

To support orchestration properly, execution targets need to become explicit first-class objects.

A process should not simply assume it runs "on the current machine".

Instead, the system should eventually reason about targets such as:

- `local_workstation`
- `client_machine`
- `pipeline_host`
- `render_host`
- `farm_node` (later, if relevant)

Each execution target should expose structured capabilities, not free-form assumptions.

Examples:

- Houdini availability
- supported Houdini version(s)
- Solaris availability
- Karma availability
- USD tools availability
- FFmpeg availability
- OpenEXR/OpenCV support
- access to project roots
- write permissions to publish locations
- network reachability
- sync status

This matters because process planning should eventually be able to answer:

- can this process run here?
- must it run elsewhere?
- does this target have the required environment?
- can the produced outputs be synced back cleanly?

Recommended future model:

```text
ExecutionTarget
- id
- label
- kind
- status
- capabilities
- environment profile
- reachable paths / roots
- sync policy
```

This should later be reflected in:

```text
core/pipeline/jobs/targets.py
```

## Process Taxonomy

Not all processes should be treated the same way.

We should classify them early so the UI, planner, runtime, and permissions model can stay coherent.

Recommended high-level process families:

- `build`
- `publish`
- `refresh`
- `validate`
- `export`
- `sync`
- `review`

Examples:

- `build_rig_from_guides` -> `build`
- `publish_asset_usd` -> `publish`
- `refresh_shot_assembly` -> `refresh`
- `validate_asset_readiness` -> `validate`
- `export_review_media` -> `export`
- `sync_publish_outputs` -> `sync`
- `generate_turntable_review` -> `review`

Each process should also declare behavioral flags, such as:

- deterministic or not
- local-only or remote-capable
- destructive or non-destructive
- auto-runnable or review-required
- blocking or background-friendly

This classification will later help the app decide:

- where to surface the process
- whether it can be automated
- whether it needs explicit human confirmation
- which targets can run it

## Canonical State Model

The orchestration system should use a small set of explicit states rather than growing ad hoc status labels across different screens.

### Job States

Recommended baseline job states:

- `queued`
- `planning`
- `blocked`
- `running`
- `succeeded`
- `failed`
- `cancelled`

Optional later refinement:

- `waiting_for_sync`
- `waiting_for_review`
- `partially_succeeded`

### Entity Freshness States

Recommended baseline freshness states:

- `up_to_date`
- `stale`
- `needs_review`
- `invalid`
- `missing_dependency`

Optional later refinement:

- `superseded`
- `unknown`

### Why This Matters

If we do not define these states centrally, each page will drift toward its own terminology:

- one panel says `outdated`
- another says `dirty`
- another says `deprecated`
- another says `needs update`

That creates confusion very quickly.

These states should eventually live in a shared place and be reused everywhere.

## Authority And Source Of Truth

As orchestration grows, we need to define what information is canonical and who is allowed to author it.

This is one of the most important structural questions.

### Questions We Need To Answer

- what makes a publish official?
- what marks an entity as stale?
- where does job history live?
- is stale state local, shared, or recomputed?
- can remote execution results become the canonical state directly?

### Recommended Direction

The safest initial model is:

- entity definitions come from project/pipeline data
- process definitions come from the app registry
- job execution records are stored explicitly
- freshness/stale state is derived from dependency rules plus known outputs
- UI never becomes the source of truth

In practice:

- widgets display state
- controllers request state
- `core/pipeline` computes or loads state
- execution backends report results
- result registration updates the shared model

This avoids hidden authority scattered across pages or controllers.

### Initial Source-of-Truth Rule

For the first implementation passes:

- registered process definitions are canonical
- job records are canonical for execution history
- dependency graph rules are canonical for impact analysis
- freshness state is derived, not manually edited in UI

That is a strong enough starting point without overcomplicating persistence too early.

## Observability And Audit Trail

If the launcher starts running important production processes, observability stops being optional.

Every process execution should leave a readable trail.

Minimum expectations:

- start time
- end time
- execution target
- process definition id
- target entity/context
- key parameters
- status
- logs
- outputs produced
- failure reason if any

This should support both:

- human debugging
- pipeline traceability

If an artist asks:

> Why is this shot stale?

or

> Which machine generated this publish?

the launcher should eventually be able to answer that clearly.

Recommended long-term direction:

- structured logs for jobs
- readable summary logs for artists
- linkage between entity and job history
- surfaced failure reasons in the UI

This is another reason job runtime and process logic must stay centralized rather than hidden in scattered scripts.

## Implementation Rollout

To keep this realistic and clean, we should roll it out in a disciplined order.

### Rollout Stage 1

Build the vocabulary only.

Deliver:

- entity models
- process definition models
- execution target models
- job models
- state enums / status vocabulary

No real process execution yet.

### Rollout Stage 2

Build read-only dependency and impact analysis.

Deliver:

- graph resolver
- upstream/downstream traversal
- stale classification
- tests for impact analysis

Still no real execution required.

### Rollout Stage 3

Expose orchestration state in the asset manager.

Deliver:

- dependency summary
- stale state summary
- available process list for selected entity

At this stage, the system should already create useful visibility even before it runs jobs.

### Rollout Stage 4

Add a shared local job runtime.

Deliver:

- queue
- status updates
- logs
- result records

Execution remains local-first, but models must already support target-aware design.

### Rollout Stage 5

Register a small set of safe deterministic processes.

Recommended first candidates:

- review/export generation
- derived media/package refresh
- controlled USD publish or assembly refresh

Not recommended yet:

- fragile animation rebuild chains
- high-risk groom rebuilds
- anything with too many implicit assumptions

### Rollout Stage 6

Integrate target-aware execution with the client/server area.

Deliver:

- target selection
- target capability checks
- remote job visibility
- sync-aware result retrieval

At this stage, the client/server panel becomes part of the operational execution story.

### Rollout Stage 7

Introduce optional automation.

Deliver:

- auto-marking stale downstream entities
- suggested refresh chains
- selective safe auto-runs

This should happen only after visibility, contracts, and logs are trustworthy.

## Final Planning Rule

If we compress the whole strategy into one implementation rule:

> First make processes explicit, then make dependencies visible, then make execution shared, and only after that make automation or remote orchestration more powerful.

That order is what protects the app from collapsing into brittle pipeline glue.

## Implementation Todo

To stay structurally disciplined from the beginning, the implementation should start in this exact order:

### 1. Freeze The Canonical Vocabulary

Define explicit models for:

- `Entity`
- `ProcessDefinition`
- `ExecutionTarget`
- `Job`
- `Dependency`
- `FreshnessState`
- `JobState`

This must happen before any Houdini runner, remote execution logic, or new UI surface.

### 2. Create The `core/pipeline/` Skeleton

Start with structure, not behavior:

```text
core/pipeline/
  entities/
  processes/
  graph/
  jobs/
```

The point is to establish ownership boundaries before adding logic.

### 3. Implement Models And Validation Only

The first concrete files should be:

```text
core/pipeline/entities/models.py
core/pipeline/processes/definitions.py
core/pipeline/jobs/models.py
core/pipeline/graph/models.py
```

At this stage:

- no UI coupling
- no Houdini execution
- no raw scripts
- no network/runtime orchestration

### 4. Add Contract Tests Immediately

Before integration, add tests for model validation:

```text
tests/test_pipeline_entities.py
tests/test_pipeline_process_definitions.py
tests/test_pipeline_graph_models.py
```

This keeps the vocabulary and normalization stable.

### 5. Add A Read-Only Graph Resolver

Only after the models exist:

- resolve dependencies
- inspect impacts
- classify stale state

This must remain read-only at first.

### 6. Surface Read-Only Status In The Asset Manager

The asset manager should become the first orchestration-aware UI surface.

Initially it should only show:

- dependency summary
- freshness/stale summary
- available process definitions for the selected entity

### 7. Add A Thin Process Controller

Only after the core models and graph are stable:

```text
controllers/process_controller.py
```

This controller should bridge UI context to `core/pipeline`, not own process logic.

### 8. Add Shared Local Job Runtime Later

Do not start with runtime or job execution.

Only add it once:

- process definitions are stable
- dependencies are visible
- target selection concepts are ready

### 9. Add Houdini And Distributed Execution Last

No direct `.py` / `.bat` launchers should be wired into the UI before the above exists.

Local Houdini execution, remote targets, and client/server orchestration should be built on top of the contracts, not before them.

## Initial Concrete Order

The practical first execution order should be:

```text
1. canonical models
2. contract tests
3. read-only graph
4. asset manager read-only integration
5. thin process controller
6. local job runtime
7. first safe deterministic processes
8. target-aware execution / client-server integration
9. automation
```

## Immediate Next Action

The next real implementation slice should be:

- create `core/pipeline/*`
- add the canonical models
- add the initial tests

That is the cleanest possible beginning and the best protection against future ugly refactors.

## Checkpoint

Current implementation checkpoint as of 2026-04-24:

### Done

- the orchestration vision and phased rollout are documented
- canonical pipeline models exist
- contract tests exist for those models
- a read-only dependency graph exists
- a read-only impact/freshness layer exists
- a minimal asset-manager bridge exists
- a thin `process_controller` now exists between the UI and `core/pipeline`
- the asset manager inspector now exposes:
  - pipeline freshness
  - tracked downstream outputs
  - available process definitions
  - a read-only prepared request summary for the selected process

### In Place But Still Read-Only

- entity inspection
- dependency traversal
- freshness classification
- process availability by entity kind
- prepared process request summaries

At this stage, the app can describe and surface orchestration-related information, and it can prepare a structured process request preview, but it does not execute pipeline processes yet.

### Not Done Yet

- no job runtime
- no Houdini execution backend
- no remote/client-server execution target flow
- no automation

### Current Practical Meaning

We now have the first visible orchestration layer in the app:

- the launcher can start telling the user what seems missing or stale
- the launcher can start telling the user which process types make sense for the selected entity
- the launcher can show what a selected process would target and prepare
- the launcher is no longer only a browser; it is beginning to reason about production state and next actions

### Next Recommended Step

The next clean step is:

- keep the process controller thin
- formalize process-request objects as the handoff to the future runtime
- introduce the shared job runtime only after this read-only process-preparation path feels stable

## A Safe Implementation Order Inside This App

To fit the current Skyforge structure, the cleanest implementation path is:

### Step A. Add Core Models First

Start with:

- `core/pipeline/entities/models.py`
- `core/pipeline/processes/definitions.py`
- `core/pipeline/jobs/models.py`
- `core/pipeline/graph/models.py`

At this stage:

- no Houdini execution
- no UI coupling
- only tests and model contracts

This mirrors the good pattern we followed with board contracts.

### Step B. Add Read-Only Graph Resolution

Next, introduce:

- dependency relationships
- impact queries
- stale classification

The first implementation can even use a limited resolver based on known project/publish structures, as long as the result is expressed through explicit models rather than raw dicts.

At this stage, the app should be able to answer:

- what depends on this entity?
- what is stale if this changes?

Still no execution required.

### Step C. Surface Status In The Asset Manager

Before running any process, show orchestration information in the existing asset manager inspector.

That gives immediate value and forces us to make the data model readable.

For example:

- `Dependency Status`
- `Downstream Impact`
- `Available Processes`

This is a very good pressure test for whether the models are actually useful.

### Step D. Register A Few Safe Processes

Only after the read-only graph is in place should we register a few actual processes.

The first ones should be low-risk and deterministic.

Good candidates:

- generate review media
- refresh a derived preview/package
- publish a controlled USD assembly

Less ideal first candidates:

- animation rebuilds with fragile assumptions
- groom refreshes with many hidden dependencies
- any process that silently mutates too many downstream files

### Step E. Add Shared Job Runtime

Once a few safe processes exist, add the shared execution runtime.

The runtime should be generic:

- queue work
- run locally
- capture logs
- store statuses
- emit updates

The runtime should not know specific process rules.
It should execute registered process plans.

### Step F. Add Houdini Backend Adapters

Only after the above is stable should we connect actual Houdini-driven processes.

This is where we bridge into:

- `.hip` contexts
- Houdini env/bootstrap
- Solaris/APEX-specific execution patterns
- structured output/result reporting

The key rule here:

The Houdini integration should be an execution backend, not the architecture itself.

## How To Avoid Monolithic Scripts In Practice

The biggest practical risk is that orchestration becomes:

- one huge controller
- one huge Houdini runner script
- one huge pile of path heuristics

To avoid that, implementation should follow these boundaries:

### Boundary 1. Process Definition vs Execution

The process definition should say what a process is.
The execution backend should only know how to run it.

### Boundary 2. Graph Resolution vs UI Presentation

The dependency graph should classify impacts.
The UI should only render those results.

### Boundary 3. Runtime vs Domain Rules

The job runtime should manage queueing/logging/status.
It should not decide what is stale or what depends on what.

### Boundary 4. Houdini Adapters vs Generic Pipeline Core

Anything Houdini-specific should live behind adapters.
The generic pipeline model should remain usable even if a future process is not Houdini-based.

## What We Should Not Do Yet

To keep the implementation clean, we should explicitly avoid these early mistakes:

- do not let pages launch raw `.py` or `.bat` scripts directly
- do not make the board the owner of process orchestration
- do not put dependency rules in `main.py` or page widgets
- do not infer everything only from filenames if we can create explicit models
- do not start with auto-rebuild chains before we have readable stale/impact inspection

## Initial Concrete File Plan

If we start the first implementation pass soon, the initial file list should probably be:

```text
core/pipeline/entities/models.py
core/pipeline/processes/definitions.py
core/pipeline/processes/registry.py
core/pipeline/graph/models.py
core/pipeline/graph/resolver.py
core/pipeline/graph/impact.py
tests/test_pipeline_process_models.py
tests/test_pipeline_graph.py
controllers/process_controller.py
ui/widgets/process_impact_panel.py
```

That is already enough to begin integrating the orchestration vision into the real app without overcommitting to execution too early.

## Practical Organization Rule

If we summarize the organization strategy in one line:

> Put orchestration intelligence in `core/pipeline`, keep controllers thin, keep widgets passive, and treat Houdini execution as a backend adapter rather than the center of the architecture.

That rule should help us stay aligned as this system grows.
