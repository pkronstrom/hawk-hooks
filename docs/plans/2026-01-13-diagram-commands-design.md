# Diagram Commands Design

**Date**: 2026-01-13
**Status**: Approved

## Overview

Two slash commands for generating technical diagrams:

| Command | Purpose |
|---------|---------|
| `/diagram-spec` | Interactive brainstorming → JSON spec |
| `/diagram-render` | Spec → Excalidraw JSON or Mermaid |

## Command 1: `/diagram-spec`

### Behavior

Interactive brainstorming-style command that asks adaptive questions until it has a clear mental model of what the user wants to diagram.

**Question areas:**
- System purpose and scope
- Diagram type (C4 container, sequence, flowchart, etc.)
- Actors and users
- Services and components
- Data stores (databases, queues, caches)
- External integrations
- Key data flows and interactions
- Logical groupings / bounded contexts
- Layout preferences

Questions are adaptive - minimal for simple diagrams, more thorough for complex systems.

### Output

- **File:** `docs/diagrams/<name>.spec.json`
- **Preview:** Show in chat if under ~50 lines
- **Clipboard:** `cat docs/diagrams/<name>.spec.json | pbcopy`
- **Follow-up:** Offer to invoke `/diagram-render`

### JSON Spec Schema

```json
{
  "title": "System Name",
  "diagramType": "c4-container | c4-context | sequence | flowchart | state",
  "description": "Optional description of what this diagram shows",
  "nodes": [
    {
      "id": "unique-id",
      "label": "Display Label",
      "type": "actor | service | db | queue | cache | external | browser | mobile",
      "group": "optional-group-id",
      "description": "Optional tooltip/details"
    }
  ],
  "edges": [
    {
      "from": "source-id",
      "to": "target-id",
      "label": "verb phrase describing interaction",
      "style": "solid | dashed | dotted"
    }
  ],
  "groups": [
    {
      "id": "group-id",
      "label": "Bounded Context / Subsystem",
      "contains": ["node-id-1", "node-id-2"]
    }
  ],
  "layout": {
    "direction": "LR | TB | RL | BT",
    "gridSize": 20,
    "groupPadding": 80
  }
}
```

## Command 2: `/diagram-render`

### Behavior

Takes a spec file and converts it to either Excalidraw JSON or Mermaid syntax.

**Process:**
1. Ask which spec to render (or accept path as argument)
2. Ask format: Excalidraw or Mermaid
3. Apply embedded best practices for chosen format
4. Generate output file
5. Provide editor links

### Output

- **File:** `docs/diagrams/<name>.excalidraw` or `<name>.mmd`
- **Preview:** Show in chat if short
- **Clipboard:** `cat docs/diagrams/<name>.excalidraw | pbcopy`
- **Editor links:**
  - Excalidraw: `https://excalidraw.com/#json=<base64>` or `https://excalidraw.com`
  - Mermaid: `https://mermaid.live/edit#base64=<encoded>`

### Excalidraw Best Practices (Embedded)

**Canvas & Layout:**
- 16:9 canvas (approx 1600×900 bounds)
- Grid size: 20px
- 80px padding between groups
- Left-to-right or top-to-bottom flow

**Shapes & Connections:**
- Arrows bound to source/target shapes (not floating)
- Orthogonal/elbow connectors for clean routing
- Labels centered on arrows
- 1-2 line labels max, no overlaps

**Visual Consistency:**
- Single diagram style (don't mix C4 with UML)
- 1-2 stroke widths only
- Minimal color palette
- Consistent naming (Title Case)
- Each view in its own frame

**Structure:**
- Frames for diagram views (Context, Container, Component)
- Groups for bounded contexts / subsystems
- Align and distribute consistently

### Mermaid Best Practices (Embedded)

**Syntax by Type:**
- Flowchart: `flowchart LR` with subgraphs
- Sequence: `sequenceDiagram` with participants
- C4: Uses `C4Context`, `C4Container` directives

**Layout:**
- Direction hints: `LR`, `TB`, `RL`, `BT`
- Subgraph groupings for bounded contexts
- Arrow labels with `|label|` or `--label-->`

### Library Recommendations

**C4 Architecture (Recommended):**
- GitHub: excalidraw-c4-library (C4 template shapes)
- Provides: Person, System, Container, Component shapes

**Cloud Icons:**
- AWS Architecture Icons library
- Azure Icons library
- GCP Icons library

**Generic:**
- Excalidraw's built-in library browser (`+` button → Browse libraries)

## File Locations

```
examples/prompts/
├── diagram-spec.md      # ~150-200 lines
└── diagram-render.md    # ~200-250 lines (more embedded knowledge)

docs/diagrams/           # Output directory (created as needed)
├── *.spec.json          # Intermediate specs
├── *.excalidraw         # Excalidraw scenes
└── *.mmd                # Mermaid diagrams
```

## Usage Flow

```
User: /diagram-spec

AI: What system are you diagramming?
User: Our payment processing service

AI: What type of diagram? (C4 container, sequence, flowchart...)
User: C4 container

AI: What are the main actors/users?
...continues until clear...

AI: Here's your spec:
    [JSON preview]
    Written to: docs/diagrams/payment-service.spec.json
    Copy: cat docs/diagrams/payment-service.spec.json | pbcopy

    Run `/diagram-render` to convert to Excalidraw or Mermaid?

User: /diagram-render

AI: Which spec? (or path)
User: payment-service

AI: Format? (Excalidraw / Mermaid)
User: Excalidraw

AI: [Generates Excalidraw JSON]
    Written to: docs/diagrams/payment-service.excalidraw
    Copy: cat docs/diagrams/payment-service.excalidraw | pbcopy
    Open: https://excalidraw.com/#json=...

    Tip: Import the C4 library for professional shapes:
    https://github.com/...
```

## Implementation Notes

- Prompts are self-contained with embedded knowledge
- No external dependencies or tool requirements
- Works offline (embedded syntax references)
- Library recommendations are suggestions, not requirements
