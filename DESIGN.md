# DecisionDoc AI Design Direction

## Purpose
This file defines the visual and interaction direction for DecisionDoc AI static and PWA surfaces.

Use this as guidance when changing:
- `app/static/index.html`
- `app/static/offline.html`
- `app/static/manifest.json`
- `app/static/sw.js`
- empty, loading, offline, install, export-adjacent static UI states

This file is visual guidance only.

It must not override:
- API contracts
- auth and tenant semantics
- approval workflow rules
- storage or provider architecture

## Product Tone
DecisionDoc AI should feel like:
- a trusted document operations desk
- a public-sector-ready writing and approval environment
- calm, capable, and structured

It should not feel like:
- a flashy startup landing page
- a neon AI toy
- a generic purple SaaS clone
- a social or chat-first product

## Core Aesthetic

### Keywords
- trustworthy
- editorial
- operational
- precise
- calm
- Korean-document-first

### Visual Metaphor
Think:
- modern document studio
- approval desk
- review binder
- controlled operations console

Not:
- futuristic dashboard overload
- gradient-heavy hype product
- consumer social app

## Audience Context
Primary users are closer to:
- operators preparing formal documents
- reviewers and approvers
- teams handling public or enterprise paperwork

The UI should reduce anxiety and increase confidence.
It should signal:
- order
- progress
- traceability
- seriousness

## Layout Principles

### 1. Lead with structure
Show the user:
- what they are doing
- what type of document they are creating
- what is required next

Before showing:
- decorative hero effects
- large gradients
- playful UI flourishes

### 2. Treat forms as a work surface
The main form should feel like a document preparation desk, not a marketing funnel.

Preferred traits:
- clear sectional grouping
- strong label hierarchy
- generous whitespace between sections
- visible required/optional distinction
- obvious primary action

### 3. Keep trust signals near the work
Important signals should stay close to inputs and actions:
- autosave or draft status
- validation state
- approval/export readiness
- offline/online state
- PWA install state

### 4. Use visual emphasis sparingly
One strong accent is enough.
Status, risk, approval, and offline states should remain easy to distinguish.

## Color Direction

### Primary palette
Avoid the current default leaning toward purple-first branding.
Prefer a more credible palette built around ink, paper, and controlled teal-blue accents.

Suggested tokens:

```css
:root {
  --bg: #f4f1ea;
  --bg-elevated: #fbf9f4;
  --surface: rgba(255, 252, 245, 0.86);
  --surface-solid: #fffdf8;
  --text: #1f2937;
  --text-strong: #111827;
  --muted: #5b6472;
  --border: rgba(99, 115, 129, 0.24);

  --accent: #0f766e;
  --accent-strong: #115e59;
  --accent-soft: rgba(15, 118, 110, 0.12);

  --ink-blue: #1d4e89;
  --approval: #166534;
  --warning: #b45309;
  --danger: #b91c1c;
  --offline: #475569;
}
```

### Usage rules
- background should feel warm and paper-like, not stark white
- primary action should use `--accent`
- headings should use `--text-strong`
- borders should stay visible but soft
- warnings and errors should be clear without overwhelming the page

### Avoid
- purple as the default brand anchor
- bright cyan + purple combinations
- pure black on pure white everywhere
- more than one competing accent family in a single viewport

## Typography

### Direction
Use Korean-friendly typography with an editorial feel.
Favor:
- Pretendard
- SUIT
- MaruBuri for selective heading emphasis if introduced intentionally

Suggested hierarchy:
- headings: dense, confident, slightly tighter tracking
- body: clear, neutral, readable
- labels: compact and explicit
- metadata: smaller, cooler, more restrained

### Rules
- no generic `Inter-only` personality
- no oversized marketing-style hero copy for operational screens
- line-height should support long Korean text comfortably
- labels should read like field instructions, not decorative captions

## Component Direction

### Hero
The hero should become a context banner, not a marketing billboard.

Preferred:
- short product purpose
- current mode or capability cue
- quiet visual depth

Avoid:
- giant gradient spectacle
- excessive badge clutter
- inflated AI hype wording

### Bundle cards
Bundle cards should feel like document type selectors.

Preferred:
- icon or mark
- strong title
- one-line use description
- compact category pill
- selected state with confident outline and mild lift

Avoid:
- playful toy-card energy
- oversized hover scale
- too many decorative gradients

### Forms
Forms are the core experience.

Preferred:
- section dividers that feel like a document chapter
- slightly elevated paper surface
- clear field groups
- calm focus ring
- readable textarea rhythm

Avoid:
- input styling that feels too glossy or app-store-like
- weak label contrast
- busy backgrounds behind text entry

### Status surfaces
Offline, install, sync, save, and validation UI should look operational and legible.

Preferred:
- horizontal notice bars or compact cards
- icon + short explanation + next action
- different tone for info, warning, offline, and success

Avoid:
- modal spam
- floating bubbles with low contrast
- oversaturated alerts

## Motion

### Preferred motion
- short fade and rise on section entry
- small lift on card hover
- subtle highlight on selection
- restrained banner slide-in for install/offline notices

### Avoid
- springy toy motion
- long parallax hero effects
- continuous animated gradients
- motion that competes with form completion

## PWA-Specific Direction

### Offline screen
The offline screen should feel dependable, not generic.

Preferred structure:
1. clear offline state title
2. one calm explanation
3. one primary retry action
4. optional note about cached content or draft safety

Tone:
- operational
- reassuring
- concise

### Install banner
The install banner should look like a productivity enhancement, not an ad.

Preferred copy themes:
- faster access
- app-like workspace
- offline continuity

Avoid:
- pushy install marketing
- novelty framing

## Content Style

### Prefer
- direct Korean copy
- action-oriented labels
- document and approval terminology
- status messages that explain next action

Examples:
- `문서 유형 선택`
- `작성에 필요한 핵심 정보를 입력하세요`
- `초안은 저장되었으며 검토 전 상태입니다`
- `오프라인 상태에서는 캐시된 화면만 확인할 수 있습니다`

### Avoid
- vague AI slogans
- playful chat-style UX copy
- overpromising automation language

Avoid examples:
- `마법처럼 문서를 만들어보세요`
- `AI가 모든 걸 해결합니다`
- `지금 바로 시작하는 놀라운 경험`

## Accessibility Rules
- maintain visible focus states
- preserve high contrast for labels and buttons
- do not rely on color alone for status
- keep touch targets large enough for mobile PWA use
- preserve readable spacing for long Korean content

## Implementation Checklist
- [ ] replace purple-first tokens with trust-oriented tokens
- [ ] reduce marketing-style hero weight
- [ ] make the main form read like a structured document work surface
- [ ] unify status components for install/offline/validation states
- [ ] keep PWA surfaces visually aligned with the main app
- [ ] preserve accessibility and existing PWA behavior

## Hard Don'ts
- do not turn the UI into a generic AI landing page
- do not overuse purple gradients
- do not introduce chat-first framing into static shell surfaces
- do not make approval or operational states look playful
- do not trade readability for visual novelty
