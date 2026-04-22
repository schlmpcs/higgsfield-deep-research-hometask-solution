# Eval Viewer Redesign Brief

This brief describes the current `viewer.html`, the information architecture it
must preserve, and a prompt you can use in Stitch to redesign it in a more
premium Higgsfield-like direction.

Design direction references:

- Higgsfield positions itself as a cinematic, creator-first AI platform focused
  on polished motion, professional creative tooling, and premium visual output.
- The public product language emphasizes cinematic control, creator workflows,
  fashion/editorial aesthetics, and high-end media production rather than a
  generic enterprise dashboard.
- Source references used for this brief:
  - https://higgsfield.ai/
  - https://higgsfield.ai/about
  - https://openai.com/index/higgsfield/

## What The Current Viewer Is

The current viewer is a self-contained static HTML file generated from eval run
artifacts. It is an inspection tool for one suite run, not a marketing page and
not a live app shell.

Its core job is to help an engineer quickly answer:

- Which cases failed?
- Which repeat failed?
- Why did it fail?
- What did the agent actually do?
- Which artifact files back up that conclusion?

## Current Information Architecture

The page is a two-column layout.

- Left sidebar:
  - suite run id
  - compact suite summary stats
  - vertical case list
- Main content:
  - selected execution header
  - repeat switcher
  - execution summary stats
  - question and final answer
  - citations
  - metric results
  - artifact paths
  - full message timeline with expandable tool details

Mobile behavior collapses the grid into a single column with the sidebar on top.

## What Data The Viewer Already Exposes

For each suite run:

- suite run id
- generated time
- aggregate summary:
  - pass rate
  - passed executions
  - total executions
  - total cost
  - p50 latency
  - p95 latency
  - mean tool calls

For each case group:

- case id
- overall pass or fail
- pass count across repeats
- repeat count

For each execution:

- case id
- repeat index
- pass or fail
- question
- final answer
- citations
- stopped reason
- error if present
- wall time
- cost
- tool count
- metric list
- failed metric subset
- artifact paths
- full message list
- normalized trace payload

## What The Current UI Looks Like

The current design is functional but conservative:

- warm beige paper-like background
- serif typography
- card-based panels with soft borders
- green pass badges and red fail badges
- sticky left sidebar
- stacked sections in the main pane
- raw JSON shown in `pre` blocks
- minimal interaction beyond case selection, repeat switching, and `details`
  disclosure elements

It reads more like an internal inspection document than a premium product UI.

## Strengths To Preserve

- The viewer is easy to understand.
- It makes failures visible quickly.
- It is static and portable.
- It exposes raw evidence, not just summaries.
- It keeps the question, answer, metrics, and timeline in one place.

## Weaknesses To Fix In The Redesign

- The visual language is too soft, muted, and editorial for a modern AI tool.
- The hierarchy is flat; the most important signals do not dominate enough.
- The case list is useful but visually plain.
- The metrics section is text-heavy and not scannable enough.
- The message timeline is useful but looks like raw logs rather than a crafted
  debugging experience.
- Artifact paths and JSON payloads feel dumped rather than designed.
- There is no strong visual framing for "suite health", "selected failure", or
  "evidence trail".

## Product Intent For The Redesign

Redesign the viewer as a premium evaluation control room for an AI research
agent. The result should feel closer to a cinematic creative tool than a
default admin dashboard.

The UI should communicate:

- precision
- speed
- confidence
- cinematic polish
- creator-tool energy
- premium software quality

It should still feel utilitarian and inspection-first. This is not a landing
page. It is an internal debugger and evaluator cockpit.

## Higgsfield-Like Visual Direction

Use Higgsfield as inspiration at the level of mood and product posture:

- cinematic and high-contrast
- polished, premium, and slightly dramatic
- modern creative-tool feel rather than enterprise SaaS
- rich visual depth, subtle glow, layered surfaces, and motion-aware layout
- strong hero summary area
- premium cards that feel like control panels
- typography with a fashion/editorial edge paired with sharp UI text
- visual emphasis on outcomes, pacing, and control

Avoid:

- purple-on-white AI startup cliches
- generic Tailwind dashboard look
- flat grey admin tooling
- overly playful neon cyberpunk
- overly dark unreadable panels

## Recommended UX Structure

Keep the same underlying content, but reorganize the experience like this:

1. Top command strip
   - suite run id
   - run date
   - pass rate
   - cost
   - latency
   - number of failing cases

2. Left rail or floating navigator
   - searchable or filterable case list
   - failure-first ordering
   - each case item shows status, repeats, and small sparkline or compact stats

3. Main hero panel for selected execution
   - large status chip
   - case id and repeat
   - question
   - short execution KPIs
   - stop reason
   - optional "what went wrong" summary block when there are failures

4. Evidence grid
   - final answer card
   - citations card
   - metric breakdown card
   - artifacts card

5. Timeline section
   - visually distinct step cards
   - assistant and tool messages styled differently
   - tool inputs and outputs in designed drawers/tabs
   - code and JSON blocks look intentional, not default browser `pre`

6. Optional normalized trace section
   - hidden by default
   - available as advanced inspection

## Required Functional Requirements

The redesign must preserve these behaviors:

- works as a single static HTML file
- no backend required
- can render all current payload fields
- case selection from the run payload
- repeat selection for cases with multiple executions
- clear pass or fail signaling
- failures sorted before successes
- readable question, answer, and error states
- metric details expandable
- timeline supports long structured outputs
- mobile layout remains usable

## Component Inventory For Stitch

Ask Stitch to produce these component types:

- app shell
- command bar
- summary KPI cards
- case rail list item
- status chips
- execution hero card
- metric cards with pass/fail styling
- citations list
- artifact reference list
- timeline step cards
- collapsible structured data drawers
- empty states
- error state card

## Copy / Tone Guidance

Tone should be:

- crisp
- technical
- product-grade
- not chatty
- not academic

Labels should stay short and operational:

- Pass rate
- Failing cases
- Tool calls
- Metric failures
- Final answer
- Evidence
- Timeline
- Tool output

## Stitch Prompt

Use this prompt directly in Stitch:

```text
Design a premium static HTML eval viewer for an AI research agent. This is an internal inspection tool for reviewing one evaluation suite run, not a marketing page.

The product should feel inspired by Higgsfield's cinematic, creator-first aesthetic: premium, high-contrast, polished, dramatic but controlled, with the feel of a professional creative tool rather than a generic SaaS dashboard. Think cinematic software, editorial sharpness, layered surfaces, subtle glow, rich depth, and clean motion cues. Avoid purple AI startup cliches, flat enterprise dashboard patterns, or noisy cyberpunk visuals.

Primary user:
- an engineer or researcher reviewing eval results

Primary tasks:
- identify failing cases quickly
- switch between cases and repeats
- inspect the selected execution
- understand why it passed or failed
- review the evidence trail from question to final answer to metrics to raw timeline

Information architecture to preserve:
- left navigation rail with suite summary and case list
- main panel with selected execution details
- top hero/summary for the selected case
- sections for question, final answer, citations, metrics, artifacts, and message timeline
- timeline includes assistant messages, tool calls, and tool outputs
- expandable details for structured data and JSON

Data model to support:
- suite run id
- generated time
- pass rate, total passed, total executions, total cost, p50/p95 latency, mean tool calls
- case groups with pass/fail, repeat count, pass count
- execution details: case id, repeat index, pass/fail, question, final answer, citations, stopped reason, error, wall time, cost, tool count, metrics, artifacts, messages

Design goals:
- make failures visually dominant
- make the selected execution feel like a hero state
- turn raw logs into a refined debugging experience
- improve scannability of metrics and timeline
- keep the UI dense but premium
- maintain strong readability on desktop and mobile

Visual direction:
- dark or near-dark base is acceptable if readability stays excellent
- use a restrained cinematic palette: charcoal, smoke, soft bone, muted chrome, deep slate, subtle warm metal or electric accent
- typography should feel premium and modern with a slight editorial edge
- status colors must be unmistakable for pass and fail
- cards should feel like product surfaces, not default panels
- code and JSON blocks should look designed and integrated

Core components:
- sticky or semi-sticky case rail
- command bar / suite header
- KPI summary cards
- execution hero card with case id, repeat, status, stop reason, wall time, cost, tool calls
- final answer card
- citations card
- metric cards with expandable details
- artifact list
- timeline step cards with assistant/tool distinction
- collapsible structured data drawers

Interaction requirements:
- case selection
- repeat selection
- expandable details
- obvious active state
- failure-first sorting

Output:
- create a high-fidelity app-style layout
- include desktop and mobile responsive states
- emphasize premium product design and cinematic control-room energy
- keep it implementation-friendly for a single-file static viewer
```

## Shorter Art-Direction Prompt

If you want a shorter version for quick iteration:

```text
Redesign this eval viewer as a premium cinematic AI control room inspired by Higgsfield. Keep it as a static inspection tool with a left case rail and a main execution view. Make failures visually dominant, make metrics and timeline highly scannable, and give the UI a polished creator-tool feel with layered dark surfaces, sharp typography, restrained glow, premium status chips, and elegant structured-data drawers. Avoid generic SaaS dashboard patterns.
```

## Notes For Implementation After Design

When converting the Stitch output back into the actual viewer:

- keep the payload contract unchanged
- keep the viewer self-contained
- prefer CSS variables for theme control
- ensure long JSON and URLs wrap safely
- keep keyboard and mobile usability intact
- do not hide raw evidence behind too many clicks
