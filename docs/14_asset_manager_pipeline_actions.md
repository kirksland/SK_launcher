# Asset Manager Pipeline Actions

This note captures the first actionable version of pipeline execution inside the Asset Manager inspector.

## What changed

The `Pipeline` tab is no longer read-only.

It now acts as the first real pipeline action surface in the launcher:

- shows `Pipeline Status`
- shows `Available Processes`
- lets the user run the selected process
- shows the last execution result
- shows produced artifacts registered by provenance

## Current first wired flow

The first real wired process is:

- `publish.asset.usd`

It is now available for:

- `pipeline_asset`
- `library_asset`

This matters because many real projects start from source geometry detected in `Library`, then publish managed USD outputs elsewhere.

## Planning rule

The HDA does not decide project structure.

The launcher resolves:

- source path
- output path
- context

Then the HDA executes that mission.

This keeps the system layout-aware and scalable:

- the layout system interprets the real project structure
- the planner translates that into a process request
- Houdini executes without hardcoding project policy

## Current parameter planning for `publish.asset.usd`

For the current selection, the launcher resolves:

- `source`
  - prefers the selected inventory file if it is a geometry source
  - otherwise finds the best geometry source in the entity folder
- `output`
  - prefers an existing USD publish path already known by the layout
  - for a `pipeline_asset`, otherwise uses `publish/<context>/<entity>.usdnc` under the managed asset
  - for a `library_asset`, resolves the managed target side first
    - reuse an existing managed asset with the same name when present
    - otherwise create the target under the pipeline asset root resolved by the layout
  - this keeps source-side folders clean and routes published USD into the managed asset ecosystem
- `context`
  - uses the selected context when explicit
  - otherwise falls back to the first active schema context
  - finally falls back to `modeling`

## Why this is the right shape

This keeps the UI thin and the ecosystem scalable.

The Asset Manager inspector becomes:

- the contextual place where pipeline actions appear

But the real logic stays in:

- layout resolution
- process planning
- runtime execution
- provenance registration

So we avoid:

- path heuristics scattered in the UI
- one-off buttons with hidden scripts
- HDA logic that tries to infer project structure by itself

## What still comes next

This is only the first actionable slice.

Next steps:

- support more executable processes from the same panel
- expose job history per entity
- expose provenance more richly in the inspector
- make process planning more role-aware for `library`, `asset`, and `shot`
- add promotion logic from source-side entities to managed assets

## Working mental model

The Asset Manager should now be read as:

- `Library` = source-side actions
- `Assets` = managed publish actions
- `Shots` = downstream assembly and review actions

The same inspector can serve all three, but the available actions should stay role-aware.
