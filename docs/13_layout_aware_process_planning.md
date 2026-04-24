# Layout-Aware Process Planning

Date: 2026-04-25

This note clarifies how the project layout system should interact with pipeline orchestration and Houdini execution.

The goal is to keep the ecosystem flexible enough to support very different project folder structures without letting process execution become fragile or hardcoded.

## Core Rule

The layout system should be the translator between:

- the real project folder structure
- the pipeline orchestration layer
- the Houdini process execution layer

In other words:

```text
real project structure
-> detected / confirmed layout
-> resolved entity roles + source/publish paths
-> process planning
-> Houdini process execution
```

The HDA should not be responsible for understanding the whole project structure.
It should receive a clean execution request.

## Short Answer

No, I do not think `library` should automatically be treated as the one absolute source of truth for all geometry, textures, or source material.

What matters is not the folder name itself.
What matters is the role assigned by the layout system.

So the source of truth should be:

- role-aware
- layout-aware
- process-aware

not:

- path-name-aware only

## Why This Matters

Projects can be messy in very real ways:

- raw vendor geometry may live in one place
- textures may live beside it, or elsewhere
- USD may already exist in another mirror tree
- managed publishes may live in a different branch of the project
- some projects may have no explicit `library/` folder at all

If process planning assumes:

```text
library = source
assets = publish
shots = downstream
```

in a hardcoded way, the system will break the moment a project deviates.

The good news is:

we already built the right protection layer for this.

## What The Current Layout System Already Gives Us

The current system already supports:

- detection of entity roots
- role tagging through `entity_sources`
- resolution of representations
- contexts
- support for nonstandard root names

Examples in `asset_layout_sandbox` make that very clear.

### Example: `standard_pipeline`

This is the clean classic case:

- `assets/`
- `shots/`
- local publish folders

This is the easiest case.

### Example: `pipeline_plus_library`

This already shows the model we care about:

- `incoming_models/` behaving like source/library
- `production_items/` behaving like managed pipeline assets

This is exactly why we need a distinction between:

- source-facing entities
- managed production entities

### Example: `mirrored_usd_layout`

This is even more important.

Here the source-like content lives in one place:

- `source_models/...`

while USD lives somewhere else:

- `usd/assets/...`

That means a valid project may absolutely have:

- source in one branch
- publish in another branch

and still be perfectly healthy.

### Example: `messy_hybrid`

This is the strongest proof.

It mixes:

- `dropbox_from_vendor/robot_raw`
- `builds/robot/publish/...`
- `cache/usd/robot`

This is not clean "library vs assets" in folder-name terms.

But it is still interpretable if the layout layer says:

- this area is source-like
- this area is managed production
- this area is representation/cache

That is exactly why layout-aware planning matters.

## Recommended Architectural Position

### 1. `library` Is A Role, Not A Sacred Folder

In practice, `library` should mean something like:

- source-oriented
- imported or referenced material
- not necessarily already under managed publish lifecycle

But the system should not require an actual literal folder named `library`.

The role should come from the resolved layout.

### 2. Source Of Truth Depends On The Process

The source of truth is not always the same object for every process.

Examples:

- for `publish.asset.usd`, the source of truth might be:
  - an OBJ in a source-style entity
  - or a managed modeling output
  - or a known library item linked to a managed asset

- for `refresh.shot.assembly`, the source of truth is likely:
  - a published USD asset
  - not the raw OBJ in a source folder

- for review generation:
  - the source of truth may be a published output or a render result

So the better mental model is:

```text
process chooses what kind of source it needs
layout tells us where that source lives
```

not:

```text
all truth always comes from library
```

## The Right Role Of Layout In Process Planning

The layout layer should answer:

- what entities exist?
- what role does each entity play?
- where are the source files for this entity?
- where are the current publish representations?
- what contexts are available?

Then the process planner should answer:

- for this selected entity and process, what should be used as input?
- where should the output go?
- is this process allowed from this role?
- should it operate directly on this entity, or on a linked managed entity?

Then the HDA should simply receive:

- `source`
- `output`
- `context`
- maybe later `entity_id`, `role`, `publish_mode`

That is the clean split.

## So Where Does The HDA Implementation Belong?

The HDA implementation belongs at the execution edge, not at the layout edge.

That means:

### Layout Layer

Responsible for:

- mapping the project
- deciding what is `library_asset`, `pipeline_asset`, `shot`
- resolving source/publish paths

### Process Planning Layer

Responsible for:

- turning the selected entity into a process-ready request
- deciding which path becomes `source`
- deciding which path becomes `output`
- deciding whether the process is valid in this role/context

### Houdini Execution Layer

Responsible for:

- instantiating the HDA
- setting parameters
- pressing `execute`
- reporting success/failure

This means the HDA should not contain the project layout policy.

It should not try to "discover" where to publish.
That decision should already be made before execution.

## Concrete Example: Source In Library, Publish In Assets

This is exactly the kind of case you described:

- source file lives in a source-like area
- publish already exists in another managed area

That is not a problem.

That should be modeled as:

```text
source-side entity
-> managed asset target
-> published representation
```

The missing piece is not more folder assumptions.
The missing piece is an explicit planning relationship.

## What I Recommend We Add Next

We should introduce the idea of:

### Source-driven planning

For some processes, a `library_asset` can be a valid input source.

Example:

- `publish.asset.usd` from a library-style source item

But that process should still target a managed publish location.

### Managed target resolution

The planner should be able to decide:

- are we publishing back into the same entity?
- are we publishing into a linked managed asset?
- are we doing a first publish that creates managed structure?

### Role-aware permissions

Not every process should be allowed equally from every role.

For example:

- `library_asset`
  - validate source
  - promote source
  - maybe publish first USD

- `pipeline_asset`
  - validate
  - publish USD
  - export review

- `shot`
  - refresh assembly
  - export review

## What This Means For `publish.asset.usd`

The process definition should eventually stop meaning:

> take whatever path is given and write whatever output is given

and instead mean:

> given a selected entity and context, resolve the correct source and publish target according to layout and role rules, then execute the HDA with those resolved values

That is the version that scales.

## Practical Rule

The HDA should stay dumb about project structure.

The planner should stay smart about:

- role
- source selection
- publish destination
- context

That is how we stay flexible while still supporting messy projects.

## Final Summary

`library` should not be treated as the one universal truth by folder name alone.

Instead:

- the layout system identifies what is source-like and what is managed
- the planner decides which source is valid for a given process
- the execution layer simply runs the HDA using resolved inputs

That is what will let the ecosystem survive:

- standard pipelines
- mirrored USD layouts
- vendor drops
- hybrid messy projects

without hardcoding one folder structure as the only valid pipeline truth.
