# Pipeline Orchestration PR Summary

## Title Suggestion

`feature/pipeline-orchestration`

## Summary

This PR introduces the first real end-to-end version of Skyforge's pipeline orchestration layer, with a working Houdini headless execution path, a first HDA-backed process (`publish.asset.usd`), and a substantial refactor of the Asset Manager to make pipeline actions contextual, scalable, and easier to maintain.

It also includes several board stability fixes and a broader cleanup of internal controller responsibilities.

## What This PR Introduces

### 1. Pipeline orchestration foundation

This PR adds the core orchestration flow needed to move from pipeline inspection to actual process execution:

- prepared pipeline requests
- runtime process requests
- local runtime execution
- Houdini backend request planning
- structured execution results
- job status updates
- provenance recording for produced artifacts

This establishes the internal flow:

`inspection -> prepared request -> runtime request -> local runtime -> houdini backend -> execution result -> job state/provenance`

### 2. First Houdini execution backend

This PR adds the first real Houdini execution bridge on the launcher side:

- execution result models
- Houdini execution planning helpers
- request payload construction for headless execution
- a first `houdini_pipeline/process_runner.py`
- process routing for `publish.asset.usd`

The runner now supports:

- receiving a JSON request
- dispatching by `process_id`
- validating required parameters
- executing a Houdini HDA in headless mode through `hython`
- returning a structured JSON result

### 3. First HDA-backed pipeline process

This PR wires the first actual process:

- `publish.asset.usd`

It is implemented as a Houdini HDA-backed process using:

- HDA type: `justi::sf_publish_asset_usd::1.0`
- parms: `source`, `output`, `context`

The execution path now:

- resolves the source file
- resolves a managed publish output path
- passes parameters to the HDA
- triggers the HDA `execute` button
- returns structured outputs and status

This is the first successful launcher -> Houdini headless -> HDA -> USD output flow in the project.

### 4. Asset Manager pipeline actions

The Asset Manager pipeline panel is no longer read-only.

This PR introduces:

- execution of the selected pipeline process from the Asset Manager
- support for `publish.asset.usd` from the UI
- resolved preview of `source`, `output`, and `context` before execution
- run feedback in the pipeline panel
- produced artifact display after execution

The Asset Manager can now:

- inspect available processes for the selected entity
- run `Publish Asset USD`
- show execution results
- show produced artifacts

### 5. Layout-aware execution planning

This PR keeps the pipeline compatible with flexible project layouts instead of hardcoding rigid folder assumptions.

Execution planning now respects the resolved project layout and entity role:

- `library` items are treated as source-side entities
- `assets` are treated as managed publish targets
- `shots` remain downstream assembly/review contexts

For `publish.asset.usd`, this means:

- a source selected from `Library` no longer publishes back into the source folder
- publish outputs are routed toward managed asset locations under `Assets`
- the launcher prepares `source/output/context`
- Houdini executes without needing to understand the entire project structure

### 6. Provenance tracking

This PR introduces the first provenance layer for produced artifacts.

The runtime can now record:

- which source artifact was used
- which process produced the output
- which job executed it
- which entity was targeted
- which outputs were generated

This lays the groundwork for proper traceability:

`source artifact -> process run -> produced artifact -> downstream inspection`

### 7. Downstream visibility in the pipeline inspector

This PR improves how pipeline truth is surfaced back into the Asset Manager.

It now begins to expose provenance-backed downstream information, so published artifacts can appear as downstream items instead of existing only as hidden runtime knowledge.

The downstream/artifact display was also made more readable for humans.

## Major Refactors

### Asset Manager decomposition

One of the biggest parts of this PR is the progressive de-pieuvrization of `AssetManagerController`.

The Asset Manager responsibilities were split into dedicated controllers:

- `controllers/asset_browser_panel_controller.py`
- `controllers/asset_details_panel_controller.py`
- `controllers/asset_pipeline_panel_controller.py`
- `controllers/asset_project_context_controller.py`
- `controllers/asset_refresh_controller.py`

In addition, domain logic was extracted into focused modules:

- `core/pipeline/processes/execution_planning.py`
- `core/asset_selection.py`
- `core/asset_browser.py`

This significantly reduced the amount of mixed UI/business logic concentrated in `AssetManagerController` and makes future evolution much easier.

### Pipeline-related module extraction

This PR also adds or strengthens dedicated modules for:

- execution result contracts
- Houdini execution planning
- runtime job orchestration
- provenance models and registry
- pipeline process planning

## Board Fixes Included In This PR

This PR also includes several meaningful board fixes and improvements:

### Loading / rebuild stability

- fixed a board rebuild crash caused by invalid Qt render-hint calls
- prevented the board loading overlay from getting stuck during failed rebuilds
- added safer failure handling during payload application

### Shortcut restoration

Board shortcuts were restored to more natural defaults:

- `I` -> auto layout
- `G` -> contextual group/ungroup
- `Ctrl+G` -> explicit group
- `Ctrl+Shift+G` -> explicit ungroup

The grid toggle no longer steals `G`.

### Thumbnail rendering stability

Asset Manager thumbnail flicker was reduced by:

- lowering watcher refresh churn
- removing redundant detail reloads
- forcing cleaner viewport repainting
- stopping unnecessary asynchronous re-hydration on the large card views

This made the visible thumbnail rendering significantly more stable.

## UX / Behavior Improvements

This PR also improves several areas of day-to-day behavior:

- clearer pipeline execution previews before running a process
- more coherent `Library -> Assets` publish behavior
- less confusing thumbnail refresh behavior in the Asset Manager
- stronger launcher logging for pipeline execution
- more explicit downstream/artifact labeling in the pipeline inspector

## Documentation Added / Updated

This PR is backed by substantial design and implementation documentation, including:

- Houdini execution backend planning
- HDA process strategy
- asset manager pipeline ecosystem notes
- layout-aware process planning
- asset manager pipeline actions
- debt audit and architectural checkpoints

## Why This Matters

This PR moves Skyforge from:

- pipeline inspection without real execution

to:

- real contextual pipeline execution
- first headless Houdini automation
- first HDA-backed process
- first provenance-backed artifact tracking
- a much more maintainable Asset Manager architecture

It is a foundational PR for everything that comes next in the pipeline ecosystem.

## Known Limits / Follow-up Work

The following areas remain intentionally incomplete or are good candidates for follow-up work:

- internal Skyforge project folders/caches are still too visible in user project directories
- cache/backup/sync storage strategy still needs cleanup and product-level decisions
- `publish.asset.usd` is the first real executable process, but not the last
- board and `main.py` remain larger structural gravity centers than ideal
- pipeline inspector storytelling can still improve further

## Validation

Validated repeatedly during the branch with:

```powershell
python -m compileall controllers core ui main.py
venv\Scripts\python.exe -m unittest discover -s tests -v
```

The branch was kept green across refactors and feature additions.

