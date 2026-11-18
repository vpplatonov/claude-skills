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

## Leading many subagents

Subagents can spawn their own, up to three levels below the main
conversation (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; `1` turns nesting
off). For a task that will lead many subagents — a large migration, say —
prefer running the main session itself on `fable` (`/model fable` at the
start, before history builds up) over burying the lead one level down.

## The routing hook

The plugin ships a `PreToolUse` hook on the Agent tool
(`hooks/route_agent.py`) that applies a keyword version of this table to
every subagent call, whether or not this skill is running:

| Rule | Matches (description + prompt) | Model |
|---|---|---|
| `large-change` | migrate, migration, architecture, major refactor, codebase-wide, deep research, quantitative analysis | `fable` |
| `scoped-code` | fix a bug, bug fix, implement the spec, write tests | `sonnet` |
| `search-read` | `Explore` agents; search, grep, find files, read logs, summarize, run tests, classify, extract — unless the task also edits, fixes, reviews or designs | `haiku` |

- It only changes the call when a rule matches and picks a different
  model. It raises a model the caller chose but never lowers it — except
  the `search-read` rule, where mistakes are cheap.
- No rule match → the call goes through unchanged.
- `[model-override]` anywhere in the prompt → the hook leaves the call
  alone. Use it when you picked the model on purpose.
- Mode, from `- Model routing:` in the `## repo-* skills` section of
  `~/.claude/CLAUDE.md` (or the `MODEL_ROUTING_MODE` env var, which wins):
  - `rewrite` (default) — changes `model` in place and tells the main
    session what it did. The result is valid; don't retry on another
    model.
  - `deny` — blocks the call with "retry with model: X"; the main session
    retries with that model.
  - `off` — the hook does nothing.
- Each decision is logged as one line in `~/.claude/model-routing.log`
  (description's first 80 characters only, never the prompt).
- Any hook error lets the call through unchanged.

## Rules

- One subagent per task, with an explicit model. Don't change the main
  session's model mid-conversation to run a task.
- Briefs never carry real people's names or secrets beyond what the task
  needs.
- Git hand-off from `~/.claude/CLAUDE.md` applies inside subagents too:
  put it in the brief.
