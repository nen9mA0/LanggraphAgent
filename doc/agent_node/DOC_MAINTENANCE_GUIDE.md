# Agent Node Doc Maintenance Guide

This document is for agents or contributors who need to extend or revise `doc/agent_node`.

It explains the current structure, what belongs in each file, and the process to follow when updating the docs.

## Current Structure

```text
doc/agent_node/
|- README.md
|- quickstart.md
|- architecture.md
|- api_reference.md
|- DOC_MAINTENANCE_GUIDE.md
|- examples/
|  `- real_agent_demo.md
|- integrations/
|  `- claude_sdk.md
`- internals/
   `- runtime_and_state.md
```

## What Belongs Where

### Top level

Use the top level only for stable, high-signal documents that most readers need.

- `README.md`
  - directory index, reading order, and high-level constraints
- `quickstart.md`
  - fastest path to first use
  - minimal runnable examples
- `architecture.md`
  - public architecture view
  - design rules and major concepts
- `api_reference.md`
  - public surface only
  - exported types, config objects, graph-facing behavior, and supported helper functions

### `examples/`

Put runnable examples, demo walkthroughs, and setup notes for sample flows here.

### `integrations/`

Put backend-specific integration guidance here.

Examples:

- SDK-specific configuration
- provider-specific runtime options
- environment preparation
- troubleshooting for one backend

### `internals/`

Put implementation details here.

Examples:

- internal runtime lifecycle
- workspace persistence details
- reducer behavior
- protocol mapping details
- internal classes that are not meant to be treated as public API

## Documentation Principles

### 1. Accuracy first

Every meaningful statement should match the current code.

Before editing docs, verify against:

- `src/workflow_agents/AGENT_GUIDE.md`
- the relevant source files under `src/workflow_agents/`
- example entry points when documenting demos or setup

If docs and code disagree, prefer the code and update the docs.

### 2. Keep public and internal content separated

Do not mix public API documentation with internal implementation details.

Rules:

- `api_reference.md` should describe only public exports and externally usable behavior
- internal base classes, protocol adapters, and backend event mapping belong in `internals/` or `integrations/`
- if a detail is only useful when modifying implementation, it should not sit in a top-level public doc

### 3. Keep top-level docs small and stable

Top-level files should answer:

- how to start
- how the system is structured
- what the public API is

They should not become a dump for every backend-specific or experimental detail.

### 4. Prefer moving detail down instead of duplicating it up

If a topic is too detailed for a top-level file:

- move the detail into `examples/`, `integrations/`, or `internals/`
- leave a short summary and a link in the top-level document

Avoid repeating the same explanation in multiple places unless the repeated part is very small.

### 5. Remove LLM-style filler

Project docs should read like technical documentation, not generated conversation.

Delete:

- repetitive framing
- conversational filler
- duplicated explanations
- speculative statements not backed by code

Prefer short, direct statements.

### 6. Preserve important project constraints

When editing docs, do not accidentally weaken or omit the core rules of this package.

These points should stay consistent unless the code changes:

- one runtime handles at most one active turn
- downstream nodes receive only `TurnResult.final_output` by default
- runtime history persistence is optional
- `session_id` maps to the backend-native resumable identifier
- provider config reuse stays minimal rather than copying full provider directories

### 7. Update structure docs when structure changes

If you add, remove, or move documents:

- update `README.md`
- update the reading order if needed
- update links from affected documents
- remove or rewrite stale references

Do not leave renamed or split documents referenced from old entry points.

## Recommended Update Process

### Step 1. Read context

Read these first:

1. `src/workflow_agents/AGENT_GUIDE.md`
2. the target docs under `doc/agent_node/`
3. the source files that the docs describe

### Step 2. Decide the scope

Classify the change before editing:

- public usage change
- public API change
- backend integration change
- internal implementation change
- example/demo change

This classification determines where the update belongs.

### Step 3. Choose the right target file

Use this rule of thumb:

- first-use instructions -> `quickstart.md`
- public design overview -> `architecture.md`
- public exported interface -> `api_reference.md`
- runnable demo -> `examples/`
- provider/backend-specific guidance -> `integrations/`
- implementation details -> `internals/`

Create a new file only when the topic is large enough to stand alone and does not fit an existing file cleanly.

### Step 4. Edit from source truth

While writing:

- copy terminology from code where it matters
- keep names exact
- describe behavior that actually exists
- avoid guessing about future behavior

If something looks ambiguous, inspect more source before documenting it.

### Step 5. Collapse duplication

After drafting:

- remove statements repeated across multiple docs
- keep the best version in the most appropriate file
- replace duplicate paragraphs with short summaries plus links

### Step 6. Check consistency

At minimum, verify:

- file names and links are still correct
- reading order still makes sense
- top-level docs do not expose internal-only details by accident
- API docs still match current public exports from `src/workflow_agents/__init__.py`
- demo docs still match the actual example scripts

## Placement Rules For Common Changes

### If a new public export is added

- update `api_reference.md`
- update `architecture.md` only if it changes the public mental model
- update `quickstart.md` only if it changes first-use guidance

### If a new backend is added

- update `README.md`
- update `architecture.md`
- update `api_reference.md` if public config or behavior changes
- add or update a file under `integrations/`
- add internal notes under `internals/` if the runtime model changed

### If internal runtime behavior changes

- update `internals/runtime_and_state.md`
- only update top-level docs if the externally visible behavior changed

### If a demo changes

- update `examples/real_agent_demo.md`
- update `quickstart.md` only if the recommended getting-started flow changed

## When To Delete Instead Of Add

Delete or merge documents when:

- two files say nearly the same thing
- a file only contains content that belongs inside another file
- a document exists only because of a past implementation split that no longer matters
- a file is mostly stale, redundant, or overly granular

Prefer fewer, clearer documents over many thin files.

## Expected Outcome

A good documentation update should leave the directory in this state:

- entry docs stay easy to scan
- public API and internal details are clearly separated
- backend-specific material is grouped together
- examples remain runnable and concrete
- other agents can tell where new material belongs without guessing
