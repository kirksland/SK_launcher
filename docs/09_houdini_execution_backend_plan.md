# Houdini Execution Backend Plan

Date: 2026-04-24

This document defines the next integration layer between the launcher orchestration system and real Houdini-driven pipeline execution.

It is a focused companion to `docs/06_pipeline_process_orchestration_plan.md`.

The orchestration plan already defines:

- pipeline entities
- process definitions
- dependency and freshness inspection
- prepared process requests
- runtime handoff requests
- a minimal local runtime that can register jobs

What is still missing is the first real execution backend.

This document explains how Houdini should enter the system without collapsing the architecture into ad hoc scripts.

## Purpose

The goal is not to "launch Houdini somehow".

The goal is to introduce a clean backend that can:

- receive a formal runtime request from the launcher
- resolve the right Houdini execution mode
- bootstrap a controlled Houdini context
- run a registered process entry point
- return a structured result payload
- feed that result back into the launcher runtime

This is the first point where orchestration becomes real execution.

## Current Checkpoint

As of this document, the launcher can already do the following:

- inspect a selected entity in the asset manager
- list pipeline-aware processes for that entity
- prepare a read-only process request
- convert that request into a runtime handoff object
- register a local job record through a minimal shared runtime
- define structured execution result models
- build a headless Houdini execution plan from a runtime request
- return a placeholder/stub execution result from a launcher-side Houdini backend adapter
- route a runtime request through the local runtime to the Houdini backend stub
- store the returned execution result and reflect it back into the job state

What it cannot do yet:

- launch Houdini from a formal runtime request
- execute a real process
- capture execution logs/results from Houdini
- update pipeline state from produced outputs

So the next phase is not "build orchestration from scratch".

It is:

> connect the existing orchestration pipeline to a first controlled Houdini execution backend.

## Guiding Principles

### 1. Houdini Is A Backend, Not The Architecture

The architecture should remain centered on:

- process definitions
- runtime requests
- job records
- execution results

Houdini should only be one execution backend that knows how to fulfill some process definitions.

That means:

- the launcher decides what process is being requested
- the runtime decides that it should be executed through the Houdini backend
- the Houdini backend only handles bootstrapping and execution details

### 2. No Raw Script Buttons

No page or widget should call:

- random `.py`
- random `.bat`
- random `hython` command strings

directly.

Everything must still go through:

```text
ProcessDefinition
-> PreparedProcessRequest
-> RuntimeProcessRequest
-> LocalJobRuntime
-> Houdini backend
```

### 3. Houdini Processes Must Be Registered

A Houdini process should always map back to a registered process id such as:

- `publish.asset.usd`
- `refresh.shot.assembly`
- `export.review.media`

The backend should not invent new behavior on the fly.

### 4. Results Must Be Structured

The backend must return something parseable and predictable.

At minimum:

- status
- message
- produced outputs
- logs or log path
- optional payload

No "read the console manually and guess what happened".

## What We Need To Add In The Launcher

The launcher side now needs a Houdini execution layer under `core/pipeline/execution/`.

Recommended first structure:

```text
core/pipeline/execution/
  __init__.py
  houdini.py
  result.py
```

### `houdini.py`

This module should eventually:

- accept a `RuntimeProcessRequest`
- resolve a Houdini executable/profile
- build a launcher-to-Houdini payload
- invoke Houdini in a controlled way
- parse a structured result

### `result.py`

This should define a small, shared result model such as:

- `ExecutionResult`
- `ExecutionLogSummary`
- `ProducedOutput`

This keeps the runtime and backend from inventing slightly different result shapes later.

## What We Need To Add In Houdini

On the Houdini side, we should prepare a very small, explicit process runner.

Not a giant script.

Not a whole pipeline framework in one file.

Recommended direction:

```text
houdini_pipeline/
  __init__.py
  process_runner.py
  processes/
    __init__.py
    publish_asset_usd.py
    refresh_shot_assembly.py
    export_review_media.py
```

Or any equivalent internal package layout you prefer, as long as the structure stays modular.

## Houdini Runner Responsibility

The Houdini runner should do only a few things:

1. receive a serialized request payload
2. validate the requested process id
3. dispatch to the corresponding registered Houdini process implementation
4. collect the result in a structured format
5. exit cleanly with a predictable status

That means the runner is a dispatcher, not the place where every process is implemented inline.

## First Runner Contract

To avoid drift, the first Houdini runner contract should be treated as explicit and small.

### Proposed Runner Location

Recommended first location on the Houdini side:

```text
houdini_pipeline/process_runner.py
```

This path is already what the launcher-side backend preview uses for now.

That does not force the final repository layout yet, but it gives both sides one stable name to target.

### Proposed Invocation Shape

Recommended first launcher-to-Houdini call shape:

```text
hython houdini_pipeline/process_runner.py --request-json "<serialized request payload>"
```

This is enough for the first proof of concept.

Later, if the payload becomes too large, we can switch to:

```text
hython houdini_pipeline/process_runner.py --request-file "<path to json file>"
```

But we should start with the smallest usable form.

### First Runner Input Rules

The runner should assume it receives one request at a time.

It should expect:

- `process_id`
- `entity`
- `execution_target`
- `parameters`

Minimal expected payload:

```json
{
  "process_id": "publish.asset.usd",
  "entity": {
    "id": "testpipeline:pipeline_asset:tree",
    "kind": "pipeline_asset",
    "label": "tree",
    "path": ""
  },
  "execution_target": {
    "id": "local",
    "kind": "local_workstation",
    "label": "Local Workstation"
  },
  "parameters": {}
}
```

### First Runner Output Rules

The runner should always write a structured result, even on failure.

Minimal required fields:

- `status`
- `message`
- `outputs`
- `log_path`
- `payload`

The safest first rule is:

- never print raw success state as the only signal
- always return a parseable JSON result

### First Logging Rule

The runner should produce one clear log path per run whenever possible.

Even before we build fancy logging, the runner should aim to give the launcher:

- a human-readable message
- a stable log path if one exists

That will make later debugging much easier.

### First Dispatch Rule

The runner should never contain all process logic inline.

It should only do:

1. parse request
2. validate `process_id`
3. import the matching process module
4. call its entry point
5. normalize the returned result

That is the most important structural rule on the Houdini side.

## Recommended Request Contract

The launcher should eventually send a payload roughly like this:

```json
{
  "process_id": "publish.asset.usd",
  "entity": {
    "id": "testpipeline:pipeline_asset:tree",
    "kind": "pipeline_asset",
    "label": "tree"
  },
  "execution_target": {
    "id": "local",
    "kind": "local_workstation"
  },
  "parameters": {
    "context": "lookdev"
  }
}
```

This should come from `RuntimeProcessRequest`, not from UI-specific data.

## Recommended Result Contract

The Houdini side should return something like:

```json
{
  "status": "succeeded",
  "message": "USD publish completed.",
  "outputs": [
    {
      "kind": "usd",
      "path": "C:/project/assets/tree/publish/usd/tree.usd"
    }
  ],
  "log_path": "C:/project/.skyforge_cache/jobs/job_001.log",
  "payload": {
    "published_version": 12
  }
}
```

For failure:

```json
{
  "status": "failed",
  "message": "Missing Solaris node graph.",
  "outputs": [],
  "log_path": "C:/project/.skyforge_cache/jobs/job_001.log"
}
```

This matters because the launcher runtime should be able to consume the result without guessing.

## Choosing The First Houdini Entry Point

We should decide early which executable mode is the default.

Practical candidates:

- `hython`
- `hbatch`
- full `houdini.exe`

Recommended first choice:

`hython`

Why:

- scriptable
- headless
- good fit for deterministic process execution
- easier to integrate into a backend than a full interactive UI launch

This does not prevent later support for:

- opening a `.hip`
- interactive artist-driven launches
- Solaris-specific UI workflows

But the backend should start from the most automatable path.

## Recommended Houdini Process Strategy

The preferred direction is now clearer:

> author the real process logic inside Houdini, but execute it through a standard headless launcher/backend path.

In practice, that means:

- the launcher stays responsible for orchestration
- Houdini stays responsible for procedural process logic
- `hython` is the default execution mode for production-style runs
- interactive Houdini UI remains available for authoring and debugging only when needed

### The Recommended Mental Model

The launcher should not know how to publish an asset internally.

It should only know:

- which process was requested
- which entity it targets
- which execution target should receive it

Then the Houdini backend should know how to dispatch that request to a Houdini-native process implementation.

### Preferred Process Shape Inside Houdini

The strongest compromise for scalability is:

- build the process visually in Houdini
- wrap it in a stable process interface
- execute that interface headlessly

Recommended implementation forms:

- HDA process wrapper
- standardized subnet wrapper
- process-oriented hip template only when truly needed

Best long-term default:

> HDA or standardized subnet as the launcher-facing process interface.

That gives us:

- visual and procedural authoring inside Houdini
- stable inputs and outputs for the launcher
- better modularity than hand-written one-off scripts

### Why This Is Better Than Raw Scripts

This approach keeps the business logic where it belongs:

- in Solaris graphs
- in SOP/LOP/APEX/KineFX setups
- in Houdini-native process assets

Instead of rebuilding process logic in Python every time, we only need Python for:

- dispatch
- context bootstrap
- parameter passing
- result collection

### Recommended Execution Modes

#### Default Mode

- `hython`
- headless
- no UI
- deterministic process execution

This should be the normal path for:

- publishes
- exports
- assembly refreshes
- other pipeline tasks that do not need artist interaction

#### Optional Debug/Authoring Mode

- full Houdini UI
- opened only when the process needs manual inspection or authoring

This should be used for:

- debugging process graphs
- authoring HDAs/process setups
- investigating failing runs

The important rule is:

> the same Houdini process should ideally be authorable in UI and executable headlessly.

## First Safe Houdini Processes

The first Houdini-backed processes should be chosen very carefully.

Good candidates:

- `export.review.media`
- `publish.asset.usd`
- `refresh.shot.assembly`

Why these are good:

- they are easier to reason about
- they have clearer outputs
- they are more deterministic than animation/rig/groom rebuild chains

Bad first candidates:

- implicit rig rebuilds from unstable setups
- animation rebuilds that may affect artistic intent
- groom/CFX refreshes with many hidden assumptions

## Suggested Internal Separation On The Houdini Side

Each Houdini process implementation should ideally have:

- input validation
- context bootstrap
- process logic
- result building

For example:

```text
processes/publish_asset_usd.py
  validate_request(...)
  load_context(...)
  run(...)
  build_result(...)
```

That keeps each process readable and testable.

## Launcher-Side Runtime Flow

Once the backend exists, the local runtime should eventually do:

```text
RuntimeProcessRequest
-> LocalJobRuntime.submit(...)
-> job record created
-> Houdini backend invoked
-> structured result returned
-> job state updated
-> outputs registered
-> asset manager refresh / pipeline refresh
```

Important:

The runtime should remain the owner of job lifecycle.

The Houdini backend should not create or manage launcher jobs by itself.

## What We Should Not Do

To keep this clean, we should avoid:

- a single giant Houdini runner file with all process logic
- process-specific shell commands in UI code
- passing random loosely structured dictionaries from widgets
- baking launcher UI assumptions into Houdini-side scripts
- updating pipeline freshness directly from Houdini without going back through the runtime/result path

## Minimal First Implementation Slice

The first practical Houdini integration slice should be intentionally small.

### Step 1

Add shared launcher-side execution result models:

- `ExecutionResult`
- `ProducedOutput`

### Step 2

Add `core/pipeline/execution/houdini.py` with a minimal interface such as:

```python
execute_houdini_request(request: RuntimeProcessRequest) -> ExecutionResult
```

For the first pass, this can still be a placeholder/stub backend as long as the contract is real.

### Step 3

Add a tiny Houdini-side process runner that:

- reads a request payload
- recognizes a single process id
- returns a structured result

### Step 4

Wire one safe process through the whole chain.

That proves:

- launcher request creation
- runtime submission
- backend dispatch
- Houdini process execution
- result parsing
- job state update

## First Real Process Choice

If we want a strong first proof of concept, the best target is probably:

`publish.asset.usd`

### What "Publish Asset USD" Means Here

For this system, "publish" should mean:

- take a work/source context
- build the official downstream-ready USD representation
- write it to a known publish location
- optionally produce small companion outputs such as metadata or preview
- return a structured execution result

It should not mean:

- arbitrary save
- loose copy of a work file
- undefined side effects

So the first process should aim to produce something official, stable, and consumable by downstream layout/shot/render steps.

## Implementation Todo

The next Houdini backend work should start in this order:

### 1. Add Launcher-Side Execution Result Models

Create:

- `core/pipeline/execution/result.py`

Add at least:

- `ExecutionResult`
- `ProducedOutput`
- `ExecutionFailure` or equivalent simple status/message structure

This gives the launcher a stable way to understand backend results.

Status:

- done

### 2. Add The Backend Adapter Skeleton

Create:

- `core/pipeline/execution/__init__.py`
- `core/pipeline/execution/houdini.py`

This layer should:

- accept a `RuntimeProcessRequest`
- serialize a payload
- call a launcher-to-Houdini entry point
- parse the structured result

Still no real heavy process logic here.

Status:

- done

### 3. Define The First Houdini Runner Contract

Decide and document:

- where the Houdini runner lives
- how the request payload is passed
- how the result payload is returned
- how logs are written

This contract must be stable before process proliferation begins.

Status:

- next and now the most important remaining launcher/Houdini interface task

### 4. Define The First Process Interface In Houdini

For `publish.asset.usd`, decide:

- HDA wrapper or standardized subnet wrapper
- required parameters
- expected outputs
- success/failure conditions

This is the point where the Houdini-side interface becomes real.

Status:

- next

### 5. Build One End-To-End Headless Path

Only after the above:

- create one request in the launcher
- submit it through the local runtime
- dispatch to the Houdini backend
- run the first headless Houdini process
- return a structured result
- update the job state

That will be the first complete proof that the architecture holds.

Status:

- pending

### 6. Keep UI Houdini Out Of The Main Path

Do not use full Houdini UI as the default execution path.

Use it only for:

- process authoring
- debugging
- manual investigation

The standard run path should stay headless.

Status:

- active rule

## When Houdini Work Should Start

At this point, the launcher side is ready enough that Houdini-side preparation can begin.

You do not need to build the full process implementation yet.

The right first Houdini tasks are:

### Houdini Task 1

Create the first runner entry point:

```text
houdini_pipeline/process_runner.py
```

It does not need to execute real pipeline work yet.

Its first job is simply:

- accept the request
- recognize `publish.asset.usd`
- return a structured stub result

### Houdini Task 2

Choose the first process wrapper format for `publish.asset.usd`:

- HDA wrapper
- standardized subnet wrapper

Recommended default:

- HDA wrapper if the interface is already clear
- subnet wrapper if you want to prototype the graph first

### Houdini Task 3

Decide the first minimal process inputs for `publish.asset.usd`.

For example:

- asset identifier
- optional source/work path
- output publish path
- context

### Houdini Task 4

Prepare the first process graph in Houdini, but keep it tiny.

The purpose is not to solve the whole pipeline immediately.

The purpose is to prove:

- launcher request
- runner dispatch
- Houdini process wrapper
- structured result

## Practical Signal

If you want the simple answer:

> yes, this is now the moment where you can start preparing the first tiny Houdini-side runner and the first `publish.asset.usd` process wrapper.

You do not need to build the full publish logic yet.

You only need enough Houdini-side structure to let us prove the end-to-end contract cleanly.

## Recommended Immediate Next Step

Before writing any real Houdini process implementation, the cleanest next move is:

1. add launcher-side execution result models
2. add a Houdini backend module with a formal interface
3. decide the first Houdini-facing process wrapper format
4. define `publish.asset.usd` as the first real process target
5. keep the first backend call local-only and minimal

That gives us one more strong contract layer before we touch the actual Houdini-side logic.

## Relationship To The Client/Server Area

This first backend should stay local-first.

But it must already be designed so that later we can swap:

- local `hython`
- another workstation
- a pipeline host

without rewriting the orchestration flow.

So the mental model stays:

```text
launcher orchestration
-> runtime
-> execution target
-> backend adapter
-> Houdini process runner
```

This is how we keep the current work useful when distributed execution arrives later.

## Final Rule

If we compress the whole plan into one line:

> Build a Houdini backend that consumes formal runtime requests and returns formal execution results, instead of letting Houdini execution leak directly into the UI or controller layer.
