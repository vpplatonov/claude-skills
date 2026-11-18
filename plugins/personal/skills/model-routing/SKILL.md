---
name: model-routing
description: Pick the right Claude model and effort for a task, then run the task as a subagent on that model with a short self-contained brief, so the main session stays lean and never switches model mid-conversation. Includes the routing table, the escalation ladder (verify → raise effort → move up a model) and the plugin's PreToolUse hook that enforces the table on every Agent call. Invoke when starting a new task, when the user asks "which model should I use", "route this", "/model-routing", or before spawning subagents.
---

# Route each task to the right model

Based on Anthropic's guide "Which Claude model should you build with?". The
idea: don't run everything on one model, and don't switch the main
session's model mid-conversation (that rewrites the whole cached history
and can drop earlier thinking). Instead the main session classifies the
task and hands it to a **fresh subagent on the right model** with a short
written brief.

## Routing table

| Task type | Model | Effort |
|---|---|---|
| Everyday engineering, debugging, multi-PR features | `opus` | `medium` → `high` |
| Well-scoped coding: bug fix, feature iteration, spec-driven work | `sonnet` | `medium` → `high` |
| Classification, routing, tagging, high-volume extraction | `haiku` | `medium` |
| Searching files, reading logs, summarizing, running tests | `haiku` (or `sonnet`) | default |
| Chat / interactive back-and-forth | `sonnet` | `low` – `medium` |
| Docs, slides, spreadsheets | `sonnet` (`opus` for complex models or large source piles) | `medium` |
| Repeated agent tasks: investigation, review, drafting | `sonnet` | `medium` |
| Computer use, vision-heavy work | `opus` | `medium` |
| Major refactor, migration, architecture, leading many subagents | `fable` | `medium` → `high` |
| Deep research, scientific or quantitative analysis | `fable` | `medium` → `high` |
| Visual design with no code yet: home or landing page, mockup, wireframe | not a subagent — Claude Design (see below) | — |
| UI built from an existing design (mockup, Figma, Claude Design handoff): a page or a few components | `sonnet` | `medium` → `high` |
| New UI in code that needs visual judgment (layout, redesign, screenshot checks), or a design system / app-wide UI rollout | `opus` | `medium` |
| Unsure | `opus` | `medium` |

Judgment rules from the guide:
- A clear spec doesn't automatically mean `sonnet` — migrations and
  performance work can still need `opus` or `fable`.
- Small models only where a mistake is cheap to spot (search, logs,
  tagging). Code edits and judgment calls stay on the stronger model.
- Bulk delegation (one `opus` lead with parallel `sonnet` workers) only for
  work bigger than one context window.
- `opusplan` puts edits on the smaller model — the reverse of this
  advice. Don't adopt it without measuring.

## Steps

1. **Classify.** Before any work, print one block:
   ```
   Task type: <row from the table>
   Model / effort: <model> / <effort>
   Why: <one line>
   ```
   If two rows fit, take the stronger one. If the user named a model, use
   it and say so.
2. **Write the brief.** The subagent starts with an empty context and
   can't ask the user anything mid-task, so the brief must stand alone:
   - goal, in one or two sentences;
   - files, folders or URLs to look at;
   - constraints (repo rules, what not to touch, git hand-off);
   - done criteria;
   - the verification command (test, build, script) the subagent runs
     before reporting.
   Summarize what this session already knows; never write "based on the
   findings above".
3. **Spawn** the subagent with the Agent tool, `model` and `effort` set
   explicitly (`model` takes an alias: `haiku`, `sonnet`, `opus`, `fable`;
   `effort`: `low`, `medium`, `high`). Run independent pieces in parallel.
4. **Stay lean.** Read the subagent's summary, decide, and spawn the next
   step. Don't re-read everything it read; open only what you need to
   check its claims.
5. **Escalate** when the result isn't good enough, in this order:
   1. add self-verification to the brief (a test, build or script it must
      pass);
   2. raise effort one level;
   3. move up one model, starting again at a *lower* effort.
   Past `high`, try the next model up instead of `xhigh`.

## Design work

The guide has no design row; these rows are this repo's extension of its
"vision-heavy → `opus`" advice. "System design" and "architecture" stay on
the `fable` row — only UI and visual work routes here.

- **Designing a page or screen from scratch** (home page, landing page,
  mockup): don't spawn a subagent. Tell the user to make it in Claude
  Design on claude.ai, a canvas built for page and UI design where they
  can compare versions and edit directly, then bring the exported
  HTML or handoff back here.
- **Building it in code from that design**: route as "UI built from an
  existing design" (`sonnet`). The brief names the design file or export
  and says how to check the result (screenshot vs. the design, a
  responsive breakpoint list). A clear design is a spec, and a spec alone
  doesn't mean `sonnet`: a design system or a rollout across the whole app
  goes to `opus`.
- **No design exists but code is wanted now**: route as "New UI in code"
  (`opus`), and have it check its own screenshots against the brief.
- **Searching or reading UI code** (find the component, list the CSS
  files) is ordinary search: `haiku`.

## Leading many subagents

Subagents can spawn their own, up to three levels below the main
conversation (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; `1` turns nesting
off). For a task that will lead many subagents — a large migration, say —
prefer running the main session itself on `fable` (`/model fable` at the
start, before history builds up) over burying the lead one level down.

## The routing hook

The plugin ships a `PreToolUse` hook on the Agent tool
(`hooks/route_agent.py`) that applies this table to every subagent call,
whether or not this skill is running.

**Classification.** The hook asks Sonnet first: it runs
`claude -p --model sonnet --effort low` with no tools, no MCP servers and
no settings, using the prompt in `hooks/classify_prompt.md`. It sends the
`subagent_type`, the description, the requested model and the first 4,000
characters of the prompt, and gets back
`{task_type, model, effort, read_only, confidence, why}`. The prompt encodes
this table and its judgment rules: unsure means `opus`/`medium`, `haiku`
only for read-only work where mistakes are cheap, a clear spec alone
doesn't mean `sonnet`, and when two rows fit it takes the stronger one.
Each Agent call waits for the classifier: about 5 seconds in testing, at
most the timeout. Its free-text reason is never passed on, and a task type
outside the table is logged as `other`.

It falls back to the keyword rules below when the `claude` CLI is
missing, the call fails or takes longer than 20 seconds
(`MODEL_ROUTING_CLASSIFIER_TIMEOUT`, capped at 25), the reply isn't valid
JSON, confidence is below 0.6, or the verdict is `haiku` for work that
isn't cheap. `MODEL_ROUTING_CLASSIFIER=regex` skips Sonnet
entirely. The nested run sets `MODEL_ROUTING_CLASSIFYING=1`, and the hook
exits at once when it sees it, so the classifier can never recurse.

| Keyword rule | Matches (description + prompt) | Model |
|---|---|---|
| `large-change` | migrate, migration, architecture, major refactor, codebase-wide, deep research, quantitative analysis | `fable` |
| `risky-review` | a review word plus a risk area (whole words; repo and path names count too): concurrency/concurrent(ly), race(s)/race condition, lock(ing) (not `*-lock.json`, `*.lock`, lockfile or "lock file"), deadlock, mutex, thread-safe/threading/multi-thread, async/asyncio, security, auth/authn/authz/authentication/authorization, OAuth, JWT, permissions, credentials, crypto/encrypt/decrypt, injection, XSS, CSRF, secrets, schema, database, transactions, cross-cutting, performance-critical, hot path | `opus` |
| `ui-system` | design system, component library, across all components/pages/screens, the whole/entire app or UI | `opus` |
| `ui-from-design` | implement the design/mockup, from the mockup/design/Figma/wireframe/handoff, match the design, pixel-perfect | `sonnet` |
| `scoped-code` | fix a bug, bug fix, implement the spec, write tests | `sonnet` |
| `ui-visual` | home page, landing page, mockup, wireframe, UI/UX/visual design, redesign the page/UI/screen/…, page or responsive layout | `opus` |
| `search-read` | `Explore` agents; search, grep, find files, read logs, summarize, run tests, classify, extract — unless the task also edits, fixes, reviews or designs | `haiku` |

The three `ui-*` rules apply only when the task also builds or changes
something (implement, build, create, add, write, design, lay out, style,
convert, …) and never to `Explore` agents, so a search through UI code
still goes to `haiku`.

**Policy**, the same for either classifier:
- It only changes the call when the classifier picks a different model.
  It raises a model the caller chose but never lowers it, except to
  `haiku` for cheap work: the `search-read` keyword rule, or a Sonnet
  verdict of `search-read`/`classification` with `read_only: true` and no
  edit or judgment word anywhere in the task (fix, edit, modify,
  implement, refactor, patch, debug, review, decide, design, delete,
  remove, rename, create, add, write/rewrite/overwrite, commit, push,
  merge, move, install, deploy, post, apply, replace, "change/update the
  …"; most in any inflection). This applies even when no model was
  requested: haiku is never picked for non-cheap work.
- No keyword match (regex fallback) → the call goes through unchanged.
- `[model-override]` anywhere in the prompt → the hook leaves the call
  alone and doesn't call Sonnet. Use it when you picked the model on purpose.
- The hook never changes `effort`. Sonnet's effort suggestion goes to the
  log only; the main session is told the new model and the rule name.
- A Sonnet verdict of `haiku` that fails the cheap checks contradicts the
  prompt's own rules, so it is discarded (`classifier_status:
  haiku-not-cheap`) and the keyword rules decide instead.
- Mode, from `- Model routing:` in the `## repo-* skills` section of
  `~/.claude/CLAUDE.md` (or the `MODEL_ROUTING_MODE` env var, which wins):
  - `rewrite` (default) — changes `model` in place and tells the main
    session what it did. The result is valid; don't retry on another
    model.
  - `deny` — blocks the call with "retry with model: X"; the main session
    retries with that model. Only raises are denied: a verdict that would
    *lower* the requested model (or pick `haiku` when none was requested),
    from either classifier, lets the call through unchanged, since a retry
    is classified again and could flip back.
  - `off` — the hook does nothing.
- Each decision is logged as one line in `~/.claude/model-routing.log`:
  mode, requested and routed model, reason, `classifier` (`sonnet` or
  `regex`), its status and latency, and Sonnet's task type, effort and
  confidence. Only the description's first 80 characters, never the prompt.
- Any hook error lets the call through unchanged.

## Rules

- One subagent per task, with an explicit model. Don't change the main
  session's model mid-conversation to run a task.
- Briefs never carry real people's names or secrets beyond what the task
  needs.
- Git hand-off from `~/.claude/CLAUDE.md` applies inside subagents too:
  put it in the brief.
