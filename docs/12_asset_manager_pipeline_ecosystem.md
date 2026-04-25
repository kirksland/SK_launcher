# Asset Manager Pipeline Ecosystem Notes

Date: 2026-04-24

This note steps back from individual features and looks at the broader architecture of the asset manager, the detected project layout, and the emerging pipeline orchestration layer.

The main question is:

> How should `shot / asset / library` really behave in the app, and how do we turn that into a coherent production ecosystem instead of a browser with partial pipeline features?

## Short Answer

The current structure is going in the right direction, but the app is still mixing two different ideas:

- browsing project content
- reasoning about pipeline state

The layout system already gives us the foundation to separate these things cleanly:

- `library` is primarily source-facing
- `asset` is primarily production-facing
- `shot` is primarily assembly/review-facing

The orchestration layer should respect those roles instead of trying to show the same pipeline behavior everywhere.

## What The Current System Already Does Well

### 1. Layout Detection Is Becoming The Source Of Truth

The app already detects and normalizes:

- entity roots
- entity sources
- contexts
- representation folders
- entity roles

This is important because it means the launcher is no longer hardcoded only around folder names like `shots` and `assets`.

It already has a vocabulary for:

- `shot`
- `pipeline_asset`
- `library_asset`

That is a strong base.

### 2. Inventory Behavior Already Distinguishes Source vs Publish

The inventory logic already treats `library_asset` differently:

- `library_asset` shows source files
- `pipeline_asset` and `shot` show published bundles and review outputs

That is good. It matches the real production difference between:

- source collections
- managed pipeline publishes

### 3. The Pipeline Inspector Is Already Role-Aware

The current bridge does not fully treat all roles the same.

For example:

- `library_asset` does not generate missing publish placeholders
- `pipeline_asset` and `shot` do

So the app is already hinting at the right idea:

> a library item should not be judged by the same publish expectations as a managed asset or a shot

That is correct.

## What Feels Weird Right Now

This is the part you noticed while looking at `bar_double_lamp`.

If you browse `Library`, you often see things that are very clearly useful pipeline sources:

- geometry
- textures
- EXRs
- source lookdev data

But in the pipeline inspector, the interaction feels thin or partially empty.

That happens because the current orchestration layer still reasons mostly like this:

- shots and pipeline assets are production entities
- library items are only lightly inspectable sources

So today, `library_asset` feels like:

- visible in browser terms
- less meaningful in orchestration terms

That is the architectural gap.

## Why This Gap Exists

There are really two different concepts hiding inside the word "asset".

### A. Source Asset

This is what `library_asset` often is in practice:

- imported model source
- source texture set
- scan
- kitbash object
- reference material

It is not necessarily "published" yet.
It may just be raw or semi-structured input material.

### B. Pipeline Asset

This is what `pipeline_asset` is meant to be:

- an entity under production control
- something with publish rules
- something that may produce USD
- something that downstream shots should consume

This is not just "a folder with files".
It is an authored production object.

### C. Shot

A shot is not a source library item and not the same thing as an asset package.

A shot is where:

- published assets are assembled
- context-specific overrides happen
- review media is expected
- layout, lighting, and render outputs become meaningful

So really, we have a three-layer ecosystem:

```text
Library   -> source material
Assets    -> managed/published production entities
Shots     -> assembled downstream consumers
```

That is the architecture we should lean into.

## Recommended Role Model

We should formalize the roles like this.

### Library

Library should be treated as the source bank.

Typical contents:

- raw geometry
- raw texture sets
- HDRIs
- scans
- vendor assets
- source material collections

Library should support actions like:

- inspect source files
- validate source completeness
- preview textures/geometry
- promote into managed asset workflow
- maybe build a first pipeline asset from the source

But library should not automatically pretend to already be a fully published pipeline asset.

### Assets

Assets should be treated as managed production entities.

Typical contents:

- modeling work
- lookdev work
- publish folders
- USD outputs
- preview outputs
- maybe metadata and validation results

Assets should support actions like:

- validate
- publish USD
- export review media
- inspect stale status
- track downstream shot impact

This is where orchestration should feel richest first.

### Shots

Shots should be treated as downstream assemblies.

Typical contents:

- shot-level assembly
- layout
- animation caches or references
- lighting outputs
- review media

Shots should support actions like:

- refresh assembly
- inspect upstream asset freshness
- regenerate review media
- eventually run targeted update chains

## What This Means For The Inspector

The pipeline inspector should not try to tell the same story for every role.

It should adapt to the role of the selected entity.

### For Library

The inspector should be source-centric.

Recommended information:

- source health
- detected file families
- preview availability
- whether the item is already linked to a pipeline asset
- candidate actions:
  - validate source
  - create/promote pipeline asset
  - generate preview/contact sheet
  - build first USD publish only if explicitly supported

### For Pipeline Assets

The inspector should be publish-centric.

Recommended information:

- freshness
- current publishes
- missing outputs
- available processes
- downstream shot impact

### For Shots

The inspector should be assembly-centric.

Recommended information:

- assembly freshness
- upstream published assets
- missing upstream data
- review media state
- refresh actions

## Current Architectural Problem In One Sentence

Right now, the app has a good browser distinction between `library_asset` and `pipeline_asset`, but the orchestration layer still gives most of its meaning to the `pipeline_asset` side only.

That is why library browsing feels real, but library pipeline interaction still feels weak.

## What I Recommend Structurally

We should stop thinking of orchestration as one generic "pipeline panel" applied evenly to all roles.

Instead, we should think in terms of:

```text
role-aware pipeline interpretation
```

Meaning:

- same inspector frame
- different orchestration meaning by role

## Proposed Ecosystem Model

### Layer 1. Source Ecosystem

Owned by `library_asset`.

Purpose:

- represent real-world source material
- validate and preview it
- expose whether it is ready to become managed production data

Example questions:

- does this library item contain geometry?
- does it contain texture sets?
- is it complete enough to promote?
- is there already a managed asset derived from it?

### Layer 2. Managed Asset Ecosystem

Owned by `pipeline_asset`.

Purpose:

- represent production-owned assets
- carry publish state
- feed shots and downstream tasks

Example questions:

- does this asset have a USD publish?
- is its publish stale?
- what downstream consumers depend on it?
- what processes are available?

### Layer 3. Shot Ecosystem

Owned by `shot`.

Purpose:

- represent assembly and downstream context
- consume published assets
- track review and refresh state

Example questions:

- which assets are assembled here?
- is the shot assembly stale?
- does review media need regeneration?
- what upstream publish changed?

## Practical Design Recommendation

The asset manager should eventually expose three kinds of pipeline interpretation:

### Library Pipeline Mode

Not "publish expected", but:

- source inspection
- source validation
- promote-to-asset actions

### Asset Pipeline Mode

The strongest orchestration mode:

- publish validation
- publish execution
- downstream dependency tracking

### Shot Pipeline Mode

Downstream orchestration mode:

- assembly refresh
- review generation
- upstream dependency visibility

## How To Represent This In Code

The current `asset_bridge` is a useful start, but it is still too flat.

It should evolve toward something more like:

```text
core/pipeline/asset_bridge.py
  -> identify selected entity role
  -> dispatch to role-specific inspectors

core/pipeline/inspection/
  library.py
  pipeline_asset.py
  shot.py
```

Each one would know:

- what "freshness" means for that role
- which outputs matter
- which processes make sense
- which warnings are meaningful

That will be much cleaner than forcing one generic graph interpretation on everything.

## Concrete Example: `bar_double_lamp`

If `bar_double_lamp` appears under `Library`, then in orchestration terms it should likely be treated as:

- source geometry
- maybe source texture set
- maybe candidate for promotion into managed asset flow

The pipeline panel for it should probably not say:

- "missing USD publish" in the same way as a managed asset

Instead it should say things like:

- source geometry detected
- texture sources detected or missing
- no managed asset publish linked yet
- available next actions:
  - validate source package
  - create/promote pipeline asset
  - publish first USD from source (optional workflow)

If `bar_double_lamp` appears under `Assets`, then the tone changes:

- managed asset
- publish expectations apply
- downstream shot impact becomes meaningful

That is the distinction we want the app to express clearly.

## What This Implies For Process Definitions

We should not assume the same process set for all roles.

Recommended process families by role:

### Library

- `validate.asset.readiness`
- `promote.library.asset`
- `prepare.asset.source_package`
- maybe `publish.asset.usd` only if we explicitly support publish-from-library-source

### Pipeline Asset

- `validate.asset.readiness`
- `publish.asset.usd`
- `export.review.media`

### Shot

- `refresh.shot.assembly`
- `export.review.media`
- later, targeted downstream refresh actions

## Architectural Rule Going Forward

The layout system should tell us what something is.
The orchestration system should decide what that role means.
The UI should reflect that meaning instead of flattening all entity types into one generic pipeline story.

## Recommended Next Steps

### 1. Stop Treating Library As A Weak Version Of Assets

Library is not a broken asset tab.
It is a different layer of the ecosystem.

### 2. Introduce Role-Specific Pipeline Inspection

Split inspection logic by role:

- library
- pipeline asset
- shot

### 3. Add A Promotion Story

Library becomes much more useful if the app can answer:

> How does this source item enter the managed asset workflow?

That can start as read-only or lightly guided before full automation.

### 4. Keep Publish Expectations Strong Only Where They Belong

Missing publish warnings should be strongest on:

- managed assets
- shots

and more nuanced on:

- library items

### 5. Let The Asset Manager Reflect The Production Lifecycle

The app should tell a lifecycle story:

```text
Library source
-> managed asset
-> shot assembly
-> review/output
```

That is a much stronger architecture than:

```text
folder browser
+ a generic pipeline tab
```

## Final Summary

The current architecture is not wrong.
It is just at an in-between stage.

The browser side already understands that `library`, `assets`, and `shots` are different.
The orchestration side now needs to catch up and express those differences more intentionally.

The clean ecosystem model is:

- `library` = source ecosystem
- `assets` = managed publish ecosystem
- `shots` = downstream assembly ecosystem

If we keep building around that model, the asset manager can become a real production cockpit instead of only a project browser with pipeline hints.

## Checkpoint

This checkpoint records the current real state of the implementation.

### What Is Already Working

- the `Pipeline` tab in the Asset Manager inspector exists and is now actionable
- the first wired executable process is `publish.asset.usd`
- the process can be launched from:
  - `pipeline_asset`
  - `library_asset`
- the launcher now resolves before execution:
  - source
  - output
  - context
- the Houdini runner executes the HDA headlessly
- the execution result is shown back in the inspector
- produced artifacts are registered through provenance
- launcher logs now record:
  - process id
  - source
  - output
  - context
  - final status

### Important Current Behavior

When the selected entity is a `library_asset`, the publish does not write back into the source folder anymore.

Instead, the planner now targets the managed asset side:

- if a matching managed asset already exists, it publishes there
- otherwise, it resolves a target under the asset root defined by the layout

So the intended flow is now:

```text
Library source
-> managed asset publish target
-> USD output
```

That matches the architecture better than publishing beside the source files.

### What Is Still Missing

The downstream panel is not fully caught up yet.

Right now, a publish triggered from `Library` can succeed and create a managed USD output, but that new output does not always appear under `Downstream items` for the selected library entity.

Why:

- the planner knows where to publish
- the runtime knows how to execute
- provenance knows what artifact was produced
- but the inspection graph still does not fully express:

```text
library source -> managed asset publish
```

So the missing piece is not execution anymore.
The missing piece is graph visibility and relationship modeling between source-side entities and managed downstream outputs.

### Practical Meaning

Today, the Asset Manager can already do something real:

- select a source-side library asset
- publish a USD from it
- route that publish into the managed asset ecosystem

But it still cannot fully narrate that relationship back to the user in the downstream inspection.

### Next Structural Step

The next clean improvement is:

- use provenance plus planner knowledge
- register the produced managed publish as a downstream artifact of the source-side entity
- surface that relationship in `Downstream items`

That will close the gap between:

- "the process ran successfully"
and
- "the ecosystem understands what this publish now belongs to"
