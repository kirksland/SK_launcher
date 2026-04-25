# DCC Integration Architecture

## Goal

The goal is to make Skyforge the system that owns project orchestration, while DCC-specific integrations remain modular and replaceable.

This does **not** mean introducing a heavy plugin framework immediately.

It means:

- keeping project creation DCC-agnostic
- standardizing how Skyforge talks to DCCs
- reusing existing Houdini-specific bricks instead of rewriting them
- preparing a clean path for Blender, Maya, and other future integrations

## Design Principles

### 1. Skyforge owns the project

A project should not fundamentally belong to Houdini, Blender, or any other DCC.

Skyforge should own:

- project folder creation
- project structure
- scene discovery
- scene opening intent
- pipeline orchestration
- runtime policies

### 2. DCC integrations own DCC-specific behavior

Each DCC integration should only own:

- how to recognize its scene files
- how to create a scene
- how to open a scene
- how to prepare execution/runtime context
- later, how to expose DCC-specific pipeline actions

### 3. Reuse existing bricks before introducing new layers

The current codebase already contains useful Houdini-specific runtime, detection, and execution logic.

The migration should:

- move existing logic into clearer DCC boundaries when useful
- avoid duplicating working Houdini code
- avoid introducing new abstraction layers unless they remove real duplication

### 4. Keep UI changes minimal for now

The immediate goal is not a UI redesign.

The current UI already works well enough to support:

- project creation
- scene opening
- pipeline execution

This architecture effort should focus on internal communication and responsibility boundaries.

## Current Brick Map

### 1. DCC discovery and descriptors

Relevant file:

- [core/dcc.py](C:/Users/justi/Desktop/SK_launcher/core/dcc.py)

What already exists:

- `DccDescriptor`
- supported DCC ids
- supported scene extensions
- default scene filename patterns
- extension-based DCC detection

What it currently lacks:

- a runtime creation/opening contract
- any real DCC handler behavior

This is the best existing place to evolve into a DCC registry/entrypoint layer.

### 2. Scene/project filesystem helpers

Relevant file:

- [core/fs.py](C:/Users/justi/Desktop/SK_launcher/core/fs.py)

What already exists:

- project discovery
- scene file discovery
- scene labeling from extension
- file-association opening

What it currently assumes:

- scenes mostly live at project root
- opening is generic except for Houdini in `ProjectsController`

This module is useful and should remain as a low-level filesystem/discovery helper.

### 3. Project bootstrap/runtime

Relevant file:

- [core/project_runtime.py](C:/Users/justi/Desktop/SK_launcher/core/project_runtime.py)

What already exists:

- base project subdirs
- Houdini template resolution/copying
- `JOB` bootstrap script generation
- `123.py` / `456.py` generation
- `JOB_INIT_MARKER`

Current problem:

- this module is strongly Houdini-biased in naming and behavior
- it mixes neutral project runtime concerns with Houdini startup specifics

This file contains useful logic, but it should be split conceptually into:

- neutral project bootstrap
- Houdini-specific scene bootstrap

### 4. Houdini environment bootstrap

Relevant file:

- [core/houdini_env.py](C:/Users/justi/Desktop/SK_launcher/core/houdini_env.py)

What already exists:

- safe Houdini environment construction
- cleanup of conflicting Python/venv env vars
- `JOB` / `HIP` / `HOUDINI_PATH` injection

This is a solid Houdini-specific brick and should be preserved.

### 5. Project creation and opening flow

Relevant file:

- [controllers/projects_controller.py](C:/Users/justi/Desktop/SK_launcher/controllers/projects_controller.py)

What already exists:

- create project folder
- create base subdirs
- ensure initial hip exists
- create `JOB_INIT_MARKER`
- discover scenes in project
- open selected scene
- dispatch Houdini launches specially

Current problem:

- project creation and scene creation are still coupled
- opening logic is partly generic and partly Houdini-specific
- Houdini startup rules live too close to the UI/controller layer

This controller should become thinner over time and delegate scene creation/opening to DCC handlers.

### 6. Houdini process execution

Relevant files:

- [controllers/process_controller.py](C:/Users/justi/Desktop/SK_launcher/controllers/process_controller.py)
- [core/pipeline/execution/houdini.py](C:/Users/justi/Desktop/SK_launcher/core/pipeline/execution/houdini.py)
- [core/houdini_env.py](C:/Users/justi/Desktop/SK_launcher/core/houdini_env.py)

What already exists:

- headless Houdini execution planning
- runtime request payload building
- subprocess execution through `hython`
- project-aware Houdini env construction
- working `publish.asset.usd` execution path

Important conclusion:

The future DCC architecture must **not** break or duplicate this pipeline execution path.

Instead, it should recognize that:

- scene/open/create integration
- pipeline/process execution

are related, but not the same thing.

They can share the same DCC integration namespace without being forced into one abstraction too early.

## Current Architectural Problems

### 1. Houdini scene bootstrap is mixed into generic project runtime

`core/project_runtime.py` currently carries both:

- generic project setup
- Houdini-specific startup details

This makes the project model feel more Houdini-owned than Skyforge-owned.

### 2. Project creation and scene creation are coupled

`ProjectsController.create_project()` currently:

- creates the project
- creates subdirectories
- creates a Houdini scene
- writes a Houdini-specific job-init marker

That is too much responsibility for one flow.

### 3. Opening scenes is not fully standardized across DCCs

There is DCC detection, but only Houdini currently has a meaningful dedicated open flow.

### 4. Future DCC expansion would currently create conditionals everywhere

If we continue the current pattern, adding Blender or Maya will likely lead to:

- more `if descriptor.id == ...`
- more DCC-specific special cases in controllers
- more startup behavior spread across unrelated files

That is exactly what this architecture should avoid.

## Minimal Common Contract

The common contract should stay intentionally small.

It should not start by trying to solve every future need.

### Proposed minimal DCC scene contract

Each DCC integration should provide:

- `id`
- `label`
- `extensions`
- `default_scene_filename(project_name)`
- `create_scene(project_path, scene_name=None, options=None)`
- `open_scene(scene_path, project_path, options=None)`
- `supports_path(path)`

### Optional later capabilities

Not required for the first migration:

- `prepare_runtime_env(...)`
- `headless_execute(...)`
- `bootstrap_project(...)`
- `publish_capabilities`

Those can come later if and when needed.

## Recommended Structure

The goal is to keep it simple and reuse as much as possible.

### Option to aim for

Keep [core/dcc.py](C:/Users/justi/Desktop/SK_launcher/core/dcc.py) as the public registry layer, and add a small DCC runtime package:

```text
core/
  dcc.py
  dcc_handlers/
    __init__.py
    houdini.py
    blender.py
```

### Responsibilities

`core/dcc.py`

- descriptor definitions
- handler registration
- lookup by id
- lookup by extension

`core/dcc_handlers/houdini.py`

- scene creation for Houdini
- scene opening for Houdini
- reuse `build_houdini_env`
- reuse template logic where still relevant

`core/dcc_handlers/blender.py`

- scene creation for Blender
- scene opening for Blender
- minimal implementation at first

This keeps the system modular without introducing a heavy plugin framework.

## Migration Plan

### Phase 1. Introduce a DCC handler layer without changing UI

Goal:

- add a handler concept behind the current DCC descriptors
- keep existing UI and controller behavior unchanged

Work:

- extend `core/dcc.py` with handler registration/lookup
- add a minimal `HoudiniDccHandler`
- add a minimal `BlenderDccHandler`
- keep the current controller entrypoints intact

Expected result:

- no user-facing change yet
- a real common DCC contract exists

### Phase 2. Move scene creation out of `ProjectsController`

Goal:

- separate project creation from scene creation

Work:

- keep `ProjectsController.create_project()` responsible only for creating the project folder and neutral structure
- delegate initial scene creation to a DCC handler
- move Houdini-specific template/bootstrap logic into the Houdini handler

Expected result:

- new project flow is no longer implicitly “create a Houdini project”
- scene creation becomes a DCC responsibility

### Phase 3. Move scene opening behind the handler contract

Goal:

- standardize open-scene behavior

Work:

- have `ProjectsController._open_scene_file()` route through the DCC handler
- keep file-association fallback where useful
- preserve current Houdini environment setup through the Houdini handler

Expected result:

- opening logic becomes uniform
- Houdini remains supported properly
- Blender/Maya can be added without controller sprawl

### Phase 4. Keep pipeline execution separate, but aligned

Goal:

- do not break the existing Houdini pipeline runner

Work:

- leave `core/pipeline/execution/houdini.py` and `ProcessController` as-is during the first migration
- later, optionally allow DCC handlers to expose execution capabilities without forcing a merger

Expected result:

- scene lifecycle and pipeline lifecycle stay compatible
- no regression for `publish.asset.usd`

## What Should Not Be Done

### 1. Do not introduce a large plugin framework immediately

No need yet for:

- installable marketplace plugins
- dynamic plugin loading
- generic plugin capability graphs

That would add complexity too early.

### 2. Do not rewrite Houdini execution

The working Houdini runner and headless execution path already provide real value.

They should be preserved and integrated, not replaced.

### 3. Do not redesign the UI as part of this work

The current UI is good enough to support the first migration.

The architecture should change first; UI can evolve later.

### 4. Do not add project metadata files unless they become truly necessary

If the project folder structure remains sufficient for now, keep it that way.

We should resist adding JSON/manifest files unless the structure alone becomes ambiguous.

## Recommended First Implementation Slice

The safest first slice is:

1. enrich `core/dcc.py` into a real registry with handlers
2. implement `HoudiniDccHandler` using existing Houdini bricks
3. implement minimal `BlenderDccHandler`
4. route scene opening through the handler contract
5. only then refactor project creation to separate project vs scene creation

This order is intentionally conservative:

- it reuses existing code
- it avoids breaking the current UI too early
- it gives us a clean seam before changing project bootstrap behavior

## Final Recommendation

The future architecture should be:

- Skyforge owns projects
- DCC handlers own scene-specific behavior
- pipeline execution remains a separate but compatible layer
- Houdini is the first real handler, not a permanent exception

The migration should be:

- gradual
- contract-first
- reuse-heavy
- low-drama

That gives us the best chance of ending up with a system that is genuinely scalable and professional without over-architecting it.

