---
name: diagram-spec
description: Interactively design a technical diagram specification through brainstorming
tools: [claude, gemini, codex]
---

# Diagram Spec

Create a technical diagram specification through interactive brainstorming.

## Process

### Step 1: Understand the System

Ask questions **one at a time** until you have a clear mental model. Be adaptive - simple systems need fewer questions, complex systems need more.

**Core questions to cover:**

1. **What system/feature are you diagramming?** (Get the name and brief purpose)

2. **What type of diagram fits best?**
   - C4 Context - High-level system + external actors
   - C4 Container - Services, databases, queues within a system
   - C4 Component - Internal structure of a single service
   - Sequence - Interactions over time
   - Flowchart - Decision trees, process flows
   - State machine - State transitions
   - Other (let user describe)

3. **Who/what are the actors?** (Users, external systems, triggers)

4. **What are the main components?**
   - Services/APIs
   - Databases
   - Queues/message brokers
   - Caches
   - External integrations

5. **What are the key data flows?** (What calls what, with what data)

6. **Any logical groupings?** (Bounded contexts, subsystems, deployment boundaries)

7. **Layout preference?** (Left-to-right, top-to-bottom, or let AI decide)

**Stop asking when you can confidently fill out the spec schema.**

### Step 2: Generate the Spec

Create a JSON spec following this schema:

```json
{
  "title": "System Name",
  "diagramType": "c4-container",
  "description": "What this diagram shows",
  "nodes": [
    {
      "id": "unique-kebab-case-id",
      "label": "Human Readable Label",
      "type": "actor | service | db | queue | cache | external | browser | mobile",
      "group": "optional-group-id",
      "description": "Optional details for tooltips"
    }
  ],
  "edges": [
    {
      "from": "source-node-id",
      "to": "target-node-id",
      "label": "Verb phrase (e.g., 'sends order', 'queries')",
      "style": "solid | dashed | dotted"
    }
  ],
  "groups": [
    {
      "id": "group-id",
      "label": "Group Label",
      "contains": ["node-id-1", "node-id-2"]
    }
  ],
  "layout": {
    "direction": "LR",
    "gridSize": 20,
    "groupPadding": 80
  }
}
```

**Schema notes:**
- `id`: Use kebab-case, unique within the spec
- `type` meanings:
  - `actor` - Human user or role
  - `service` - Application, API, microservice
  - `db` - Database (SQL, NoSQL, etc.)
  - `queue` - Message queue, event bus
  - `cache` - Redis, Memcached, CDN
  - `external` - Third-party API or system
  - `browser` - Web frontend
  - `mobile` - Mobile app
- `edges.style`: Use `dashed` for async, `dotted` for optional flows
- `layout.direction`: LR (left-right), TB (top-bottom), RL, BT

### Step 3: Output

1. **Create directory if needed:**
   ```bash
   mkdir -p docs/diagrams
   ```

2. **Write the spec file:**
   - Filename: `docs/diagrams/<kebab-case-title>.spec.json`
   - Example: `docs/diagrams/payment-service.spec.json`

3. **Show preview:** If under 50 lines, display the full JSON in chat.

4. **Provide clipboard command:**
   ```
   Copy to clipboard:
   cat docs/diagrams/<name>.spec.json | pbcopy
   ```

5. **Offer next step:**
   ```
   Ready to render? Run `/diagram-render` to convert this to Excalidraw or Mermaid.
   ```

## Example Conversation

```
User: /diagram-spec

AI: What system or feature are you diagramming?

User: Our checkout flow

AI: Got it - checkout flow. What type of diagram would work best?
    1. C4 Container - Show services, DBs, queues involved
    2. Sequence - Show the step-by-step interaction over time
    3. Flowchart - Show decision points and branching logic
    4. Something else?

User: Sequence diagram

AI: Who initiates the checkout? (e.g., User in browser, mobile app, API client)

User: User in browser

AI: What services are involved in the checkout flow?

User: Cart service, payment service, inventory service, and Stripe for payments

AI: What's the basic flow? Walk me through the happy path.

User: User clicks checkout, cart service validates items, inventory checks stock,
     payment service charges via Stripe, then order is confirmed

AI: Any error cases or branches worth showing? (e.g., payment failure, out of stock)

User: Yes, show payment failure and out of stock

AI: That's enough to build the spec. Here it is:

    {
      "title": "Checkout Flow",
      "diagramType": "sequence",
      ...
    }

    Written to: docs/diagrams/checkout-flow.spec.json
    Copy: cat docs/diagrams/checkout-flow.spec.json | pbcopy

    Ready to render? Run `/diagram-render` to convert to Excalidraw or Mermaid.
```

## Tips for Good Specs

- **Use verb phrases for edge labels:** "sends request", "returns data", "publishes event"
- **Group related services:** Put microservices in a "Backend" group, external APIs in "External"
- **Keep it focused:** One diagram should tell one story. Split complex systems into multiple diagrams.
- **Name consistently:** If you call it "User" in one place, don't call it "Customer" elsewhere
