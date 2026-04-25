# Asset Manager Debt Audit

## Why This Checkpoint Exists

The Asset Manager is becoming one of the main operational surfaces of the launcher:

- project browsing
- layout-aware entity discovery
- inventory inspection
- pipeline inspection
- process execution

That makes it a high-value area, but also a place where technical debt can quietly accumulate if UI glue, layout logic, runtime orchestration, and path resolution all start mixing together.

This note captures what is already in a healthy place, what is merely acceptable for now, and what should be treated as real debt.

## What Is Already In Good Shape

### Houdini executable resolution is already settings-driven

The app does **not** hardcode a production Houdini path for runtime execution.

Current flow:

- the user-configured Houdini executable lives in settings as `houdini_exe`
- `main.py` loads it into `self._houdini_exe`
- `controllers/process_controller.py` uses that configured value
- `core/pipeline/execution/houdini.py` resolves the matching `hython.exe`

So the important runtime path is already controlled by the app settings.

### Workspace roots are already settings-driven

These are already configurable:

- `projects_dir`
- `server_repo_dir`
- `template_hip`
- `houdini_exe`
- `use_file_association`

This is good. It means the launcher is not tied to one fixed workstation layout.

### Layout-aware browsing is the right structural direction

The Asset Manager is already built around:

```text
real project structure
-> layout detection / confirmation
-> resolved entity roles
-> asset manager UI
-> pipeline planning
```

That is important because it prevents the pipeline from depending on one rigid folder layout.

## What Looks Hardcoded But Is Mostly Fine

### Houdini install discovery under `Program Files`

`core/settings.py` scans common Windows install locations:

- `C:\Program Files\Side Effects Software`
- `C:\Program Files\Side Effects Software\Houdini`

This is acceptable as a **default discovery convenience**, not as runtime truth.

The app still ultimately uses the selected `houdini_exe` from settings.

### Settings UI placeholder paths

Some placeholder/default browse roots in the Settings page still reference common Windows Houdini locations.

That is acceptable for now because they are hints for the UI, not actual execution contracts.

### Manual Houdini test helpers

Files under `tests/manual/` still contain concrete local paths such as:

- a specific `hython.exe`
- `test_pipeline` source/output paths

That is fine because they are manual debug helpers, not launcher runtime configuration.

## Real Debt We Should Track

### 1. `AssetManagerController` is carrying too much

Right now it owns a lot of responsibilities:

- project context switching
- layout onboarding
- entity list rebuilding
- preview loading
- inventory rendering
- pipeline inspection wiring
- runtime execution wiring
- file watching
- status messaging

This is still workable, but it is already too broad.

Good future split:

- `asset_browser_controller`
- `asset_inspector_controller`
- `asset_pipeline_panel_controller`
- `asset_watch_controller`

We do **not** need that refactor immediately, but we should treat it as inevitable if the Asset Manager keeps growing.

### 2. Repeated UI reset logic

There are multiple places where the controller manually resets:

- pipeline summary
- process list
- process summary
- run summary
- artifact list
- inventory/history placeholders

This is a classic drift risk:

- easy to forget one field
- easy to create inconsistent empty states
- easy to regress during future pipeline features

We should eventually centralize this into a few dedicated methods or view-state objects.

### 3. Stringly-typed targets and roles

The Asset Manager still relies on raw strings in many places:

- `"shots"`
- `"assets"`
- `"library"`
- `"shot"`
- `"asset"`
- `"pipeline_asset"`
- `"library_asset"`

This is manageable now, but it is easy to make mistakes as more contextual features arrive.

We should eventually introduce a smaller typed layer or canonical enums/constants for the UI-facing target names.

### 4. The pipeline graph shown in the inspector still lags behind runtime truth

We now have:

- planner-aware output routing
- runtime execution
- provenance capture

But the inspector downstream view does not yet fully narrate:

```text
library source -> managed asset publish
```

So the real ecosystem already knows more than the read-only graph shown in the panel.

This is one of the next meaningful product debts to address.

### 5. Context selection is still under-explained

The current effective pipeline context comes from:

- the selected context combo if specific
- otherwise the first layout context
- otherwise `modeling`

That is structurally okay, but it can feel opaque if the user did not explicitly choose it.

We already improved this by showing:

- resolved source
- resolved output
- resolved context

before execution, but longer-term we should likely make context choice more explicit for some actions.

### 6. Watcher behavior is still a sensitive area

The thumbnail flash issue exposed that the Asset Manager is sensitive to:

- watcher-triggered refreshes
- list rebuild churn
- delayed thumbnail hydration

We fixed the current visible problem, but this area should still be considered fragile.

If we add more live pipeline/job state in the same panel, we should be careful not to reintroduce churn through over-eager refresh logic.

## Recommended Next Debt Passes

### Short-term

1. Keep the current thumbnail stabilization.
2. Surface provenance/downstream links for `library -> managed asset publish`.
3. Centralize Asset Manager empty/reset view state.

### Mid-term

1. Split pipeline-specific UI behavior out of `AssetManagerController`.
2. Add a small typed layer for Asset Manager target/role names.
3. Add a minimal job history section per entity in the pipeline tab.

### Long-term

1. Split browser / inspector / watcher responsibilities into smaller controllers.
2. Move more Asset Manager state toward explicit view-model style objects.
3. Make pipeline actions fully context-aware without relying on UI heuristics.

## Bottom Line

The good news is that the most important execution path is **already settings-driven**, especially for Houdini.

The real debt is not “hardcoded `hython` everywhere”.
The real debt is mostly:

- too much responsibility in one controller
- repeated UI reset logic
- graph/provenance mismatch in the inspector
- fragile live-refresh behavior

That is a much better kind of debt to have than a launcher full of fixed workstation paths.
