---
name: init-ui-stack
description: Initialize a web UI project with React + TypeScript + Tailwind + shadcn/ui, auto-detecting backend and creating development rules
tools: [claude]
---

# Initialize UI Stack

Bootstrap a modern web UI project with React + TypeScript + Tailwind CSS + shadcn/ui. Auto-detects the backend, scaffolds the right frontend structure, and creates persistent development rules.

## Process

### Step 1: Detect Backend

Scan the project root to identify the existing backend:

```bash
# Check for backend indicators
ls pyproject.toml requirements.txt go.mod Cargo.toml package.json 2>/dev/null
```

| Signal | Backend |
|--------|---------|
| `pyproject.toml` or `requirements.txt` | Python (FastAPI/Django) |
| `go.mod` | Go |
| `Cargo.toml` | Rust |
| `package.json` with next/express deps | Node.js |
| None of the above | Standalone frontend |

Present the detection result and confirm with the user. If ambiguous, ask.

### Step 2: Choose Complexity Tier

Ask the user:

```
Which UI complexity tier?

1. Minimal — Landing page or simple form. Basic layout only.
2. Dashboard — Sidebar nav, data tables, cards, charts area.
3. Full app — Auth flow, routing, layouts, forms, dashboard + CRUD views.
```

### Step 3: Scaffold Frontend

Based on backend + tier, set up the project:

#### Frontend Approach by Backend

| Backend | Approach |
|---------|----------|
| **Python (FastAPI/Django)** | Separate `frontend/` dir with Vite + React + TS. API and frontend run on separate dev servers. |
| **Next.js / Node** | Single project. App Router with React Server Components where appropriate. |
| **Go** | Separate `frontend/` dir with Vite + React + TS. Go serves API. |
| **Rust (Axum/Actix)** | Separate `frontend/` dir with Vite + React + TS. Rust serves API. |
| **Standalone** | Next.js full-stack with App Router. |

#### Core Stack (all tiers)

Install and configure:
- React 18 + TypeScript (strict mode)
- Tailwind CSS v4
- shadcn/ui (installed via CLI, with default theme)
- Prettier + ESLint

#### Tier-Specific Additions

| Tier | What to scaffold |
|------|-----------------|
| **Minimal** | Basic `<Layout>` with header/footer, single page |
| **Dashboard** | `<Sidebar>`, `<Header>`, `<Card>`, `<DataTable>` from shadcn, chart library (recharts), dashboard layout |
| **Full app** | Everything in Dashboard + auth page stubs, form components, route structure, loading/error boundary states |

### Step 4: Create Development Rules

Create `.claude/rules/ui-development.md` in the project root with persistent rules for all future UI work:

```markdown
# UI Development Rules

## Tech Stack
- React 18 + TypeScript (strict)
- Tailwind CSS for all styling
- shadcn/ui for all UI components — never use raw <button>, <input>, etc.

## Component Conventions
- Use shadcn/ui primitives: Button, Input, Card, Dialog, Table, etc.
- Compose complex components from shadcn primitives
- Place shared components in `components/ui/` (shadcn managed) and `components/` (project-specific)
- Keep components focused — one responsibility per file

## Styling Rules
- Use Tailwind utility classes only — no custom CSS unless absolutely necessary
- Use semantic color tokens (e.g. `text-primary`, `bg-muted`) not raw colors
- Use spacing scale consistently (p-4, gap-6, etc.) — no arbitrary values
- Prefer flex/grid + gap over margins
- All layouts must be responsive (mobile-first)

## UI Quality Checklist
Before completing any UI work, verify:
- [ ] Responsive: works on mobile (375px), tablet (768px), desktop (1280px)
- [ ] Accessible: semantic HTML, ARIA labels, keyboard navigation, color contrast WCAG AA
- [ ] Consistent: matches existing spacing, typography, color patterns
- [ ] Loading states: skeleton/spinner for async data
- [ ] Error states: user-friendly error messages, not raw errors
- [ ] Empty states: meaningful content when data is empty

## Feedback Loop
When building UI, follow this cycle:
1. **Explore** — Read existing layout, design tokens, component patterns. Don't code yet.
2. **Plan** — Outline component tree, shadcn components to use, data props needed.
3. **Code** — Implement static layout first, then wire data.
4. **Self-critique** — Review as a senior frontend engineer: layout issues, spacing violations, accessibility problems, visual inconsistencies.
5. **Refine** — Fix issues found in critique.
6. **Test** — Run lint, typecheck, and verify in browser.

## Don'ts
- Don't invent new color tokens — use existing semantic tokens
- Don't use inline styles
- Don't create wrapper components around shadcn unless adding real functionality
- Don't skip TypeScript types for component props
- Don't use `any` type
```

### Step 5: Verify Setup

After scaffolding, verify everything works:

1. **Dev server** — Start the dev server and confirm it runs without errors
2. **Lint + typecheck** — Run lint and TypeScript checks, fix any issues
3. **Summary** — List everything that was installed and created:

```
UI Stack initialized:

Framework: [Vite + React / Next.js]
Location: [./frontend/ or ./]
Tier: [Minimal / Dashboard / Full app]

Installed:
- React 18 + TypeScript (strict)
- Tailwind CSS v4
- shadcn/ui with [N] components
- [tier-specific packages]

Created:
- [list of key files/directories]
- .claude/rules/ui-development.md (persistent UI dev rules)

Dev server: [command to start]
```

## Notes

- If a `frontend/` directory or existing React setup already exists, ask the user how to proceed (extend existing vs. start fresh)
- Always use the latest stable versions of packages
- The `.claude/rules/ui-development.md` file ensures consistent quality across all future Claude sessions working on this project
