# Houdini HDA Process Strategy
Date: 2026-04-24

> Houdini process logic should primarily live inside HDAs, while the launcher focuses on orchestration and communication.


## Decision

We are choosing the following direction:

```text
Primary Houdini process wrapper format = HDA
```

This means:

- the launcher does not own the real Houdini process logic
- Houdini process logic should be authored inside Houdini
- the launcher/backend should only know how to request and execute those processes cleanly

## Why HDA Is The Right Choice

Using HDAs as the main process wrapper gives us several strong advantages:

- stable interface
- visual and procedural authoring in Houdini
- reusable outside the launcher
- easier to version and evolve
- more scalable than one-off scripts

This fits the pipeline direction well:

- the launcher orchestrates
- the backend dispatches
- the HDA performs the Houdini-native work

## What We Are Actually Designing Right Now

At the current stage, we are still mostly defining:

- communication between the launcher and Houdini
- the shape of a process request
- the shape of a process result
- the role of the Houdini runner
- the role of the HDA process wrapper

So for now, the focus is on:

- contracts
- interfaces
- process vocabulary

Not yet on:

- a full Houdini directory tree
- a large library of process HDAs
- full publish logic
- distributed execution

## What The Launcher Should Know

The launcher should know only a few things about a Houdini process:

- which process id is being requested
- which entity it targets
- which execution target should run it
- which parameters are passed

Example:

```text
Process: publish.asset.usd
Entity: barstool_v1
Target: local workstation
Mode: headless hython
```

The launcher should not know:

- how the internal LOP graph is built
- which nodes are used
- how the export is implemented internally

That belongs to Houdini.

## What The HDA Should Represent

A process HDA should be treated as a stable launcher-facing process interface.

That means the HDA should eventually expose:

- clear inputs
- clear parameters
- a clear execution trigger
- clear outputs
- a clear success/failure path

The HDA can contain any internal complexity it needs, but from the launcher point of view, it should feel like a machine with a known interface.

## Headless First

The intended default execution mode is still:

```text
hython
```

That means:

- no Houdini UI by default
- process runs headlessly
- the HDA should be executable without manual interaction

Interactive Houdini UI should stay useful for:

- authoring the HDA
- debugging
- manual inspection

But it should not be required for normal launcher-driven runs.

## What We Are Not Building Yet

To stay focused, we are not asking for all of this right now:

- a full Houdini-side pipeline package
- final HDA naming/versioning conventions
- complete process catalog
- final publish/versioning policy
- remote execution wiring

Those will come later.

Right now, the only thing we really want is:

> a clean shared understanding of how launcher requests will talk to future Houdini process HDAs.

## First Practical Target

The first process we are aiming toward is:

```text
publish.asset.usd
```

At this stage, that means we will eventually want:

- one launcher-side process request
- one Houdini-side runner dispatch
- one HDA process wrapper
- one structured result

Nothing more complicated is needed yet.

## What You Do Not Need To Build Yet

Right now, you do **not** need to:

- build a full Houdini folder structure
- create many process HDAs
- solve all publish cases
- build a giant runner

We are still at the stage of agreeing on the communication model.

## What You Will Probably Need Soon

When we take the next real Houdini step, the first useful thing to prepare will likely be:

- one minimal HDA process wrapper for `publish.asset.usd`

But only after the launcher-side runner contract is nailed down enough.

## Simple Summary

If we say it in the simplest possible way:

- the launcher asks for work
- the backend passes the request to Houdini
- Houdini executes a process HDA
- Houdini returns a structured result

That is the model we are now committing to.
