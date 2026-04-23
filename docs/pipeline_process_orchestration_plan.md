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
