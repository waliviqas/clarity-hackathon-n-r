# Mina's Claude Code workspace plan (Clarity, NVIDIA x Red Hat hack)

Written Sat Oct 17, ~1:00 PM. Inputs:
- "Claude Code Agentic Workspace Guide" (PDF, 20 pp.)
- the "Hackathon Implementation Plan" prompt
- the team's latest model plan (wiki)
- research done Oct 17

**Startup (every session, automatic):** the SessionStart hook prints BrowserOS neo status + the last progress lines → Claude follows "The loop" in `CLAUDE.local.md` → guard hook checks every command → researcher / qa / reviewer agents are called when needed. Mina only reads the status line and answers questions.

Status words (same everywhere: this plan, QA reports, `docs/progress/mina.md`):
- Work: **Not started · In progress · Verified · Blocked · Failed**
- Claims: **VERIFIED** (primary source or tested here), **UNVERIFIED** (not yet checked), **REPORTED** (community claim)

## TL;DR: what runs by itself, and what Mina does

**Runs automatically, no action needed:**

| What | How |
|---|---|
| Project context, rules, contracts | `CLAUDE.md` (+ contracts import), `CLAUDE.local.md`, path rules in `.claude/rules/`, all loaded each session |
| BrowserOS neo connection check, last progress notes, friction-log reminder | `SessionStart` hook (`.claude/hooks/session-start.mjs`) |
| Secret / forbidden-file scan on every `git commit` and `git push`; block on any non-BrowserOS browser tool | `PreToolUse` hook (`.claude/hooks/guard.mjs`) |
| Blocking Claude in Chrome, other browser MCPs, reading `.env`, pushing to `main`, force-push, hard reset | deny rules in `.claude/settings.local.json` |
| No permission prompts for edits and safe commands (build, tsc, git status/diff/log/add/commit, contract validation, BrowserOS neo, web search) | `defaultMode: acceptEdits` + allow list in `.claude/settings.local.json`. Push, installs, deletes still ask |
| Research, QA, review | three agents Claude calls on its own (`.claude/agents/local/`) |
| Plan → build → QA → review → commit → progress note | "The loop" in `CLAUDE.local.md` |

**Mina's manual steps (once):**
1. Unzip the package into the repo and commit (instructions in the chat).
2. Keep BrowserOS neo open. It is already connected to Claude Code via its one-click Connect / MCP window.
3. Once: `brev login`; when the dashboard needs the bus, keep `brev port-forward <instance> --port 8080:8080` running in a terminal.
4. Optional: `scoop install gitleaks` (or `winget install -e --id Gitleaks.Gitleaks`). The guard uses it if present and has a built-in scan if not.
5. Ask Wali (repo owner) to confirm GitHub push protection is on (Settings → Code security).

No custom skill was made. The loop plus hooks covers the repeatable workflow, so a skill would only add context cost (the guide's §17 "don't create a skill when a short rule is enough").

---

## 1. Requirements breakdown

### 1a. What the PDF actually is
The PDF is **not** the hackathon's requirements. It is a guide for *configuring Claude Code*: rules, subagents, skills, hooks, BrowserOS neo research routing, QA and review, and context management.
- The hackathon's own requirements live in `docs/hackathon.md`: the 33B cap, open data, code written during the event, deadline, judging.
- The required stack comes from the team plan in `docs/architecture.md`: Brev, vLLM, Qwen3-VL-2B, Nemotron Nano 12B v2 VL, Nemotron Nano 9B v2, Nemotron Embed + Rerank, NeMo Gym.

This plan applies the PDF to *how Claude Code works for Mina*, and the hackathon rules to *what gets built*.

### 1b. Requirements from the PDF

| # | Requirement (PDF section) | Type | How it's satisfied |
|---|---|---|---|
| G1 | Inspect the repo before creating config; preserve what exists (§24) | Mandatory | Repo inspected (main had only README + .gitignore); new files added, nothing deleted |
| G2 | Smallest useful set of rules/agents/skills/hooks; don't create things just because the guide lists them (§12, §14, §17, §24) | Mandatory | 3 agents, 2 hooks, 2 path rules, 0 skills (see §4 "not created") |
| G3 | Present the proposed setup before creating substantial config (§12, §23, §24) | Mandatory | Proposed in chat and in this doc. All new config is local-only (gitignored) and easy to remove. |
| G4 | Researcher subagent for external research; browser research through BrowserOS neo; parent gets synthesis + citations + uncertainty, not transcripts (§3, §15) | Mandatory | `researcher` agent |
| G5 | Verify BrowserOS is connected before relying on it; report if unavailable (§15) | Mandatory | `SessionStart` hook checks every session |
| G6 | QA verifies meaningful features before "complete", tailored to project type (§16) | Mandatory | `qa` agent: React build + BrowserOS checks; Python fake-mode runs + contract validation |
| G7 | Independent reviewer when risk warrants; distinct from QA; one reviewer role when possible (§16) | Mandatory | One `reviewer` agent (architecture + rules + security) |
| G8 | Concise CLAUDE.md; focused rule files; CLAUDE.md answers: what, stack, build/run, constraints, security rules, which agents/hooks exist (§2, §6, §19) | Mandatory | `CLAUDE.md` (~80 lines) + `.claude/rules/` + `CLAUDE.local.md` |
| G9 | Protect secrets; no destructive automation (§21) | Mandatory | Guard hook, deny rules, §7 checklist |
| G10 | Use current Claude Code syntax where the guide is outdated (§24, p.2) | Mandatory | Syntax checked against code.claude.com docs (Oct 17). The guide's BrowserOS port and URL page are wrong for neo (§5 below). |
| G11 | Hooks only for deterministic checks; inspect command/scope/side effects; least powerful check (§18) | Mandatory | Both hooks are read-only checks (git diff/log, TCP connect, file reads); no writes, no network except localhost |
| G12 | Researcher rules: primary sources, stop when enough, compact synthesis, no credentials, approval for side effects (§15) | Mandatory | In `researcher.md` |
| G13 | Keep the BrowserOS integration out of source control; no hard-coded browser credentials (§15) | Mandatory | MCP entry lives in `~/.claude.json` (user scope); nothing BrowserOS-specific committed |
| G14 | Maintain a short status file updated each session (§22) | Recommended | `docs/progress/mina.md`, shown at session start |
| G15 | Agent budget: medium project → 2–4 agents (§14) | Recommended | 3 |
| G16 | Runtime loop: plan → research → slice → hooks → QA → review → fix → update (§20) | Recommended | "The loop" in `CLAUDE.local.md` |
| G17 | Match model/effort to the task (§11, §22) | Recommended | researcher/qa on Sonnet, reviewer on Opus, main session as Mina chooses |
| G18 | Plan Mode for substantial work (§9) | Recommended | Loop step 2 |
| G19 | Workspace bootstrap/setup workflow (§13, §24) | Recommended | Done once, by hand, in this plan; no bootstrap skill, since setup won't repeat during the hack |
| G19 | Verify security before publishing (§9) | Mandatory | §7 checklist + reviewer before final push |

### 1c. Extra requirements from the prompt (stricter than the PDF)
| # | Requirement | How it's satisfied |
|---|---|---|
| P1 | **BrowserOS neo is the only browser tool**; no Playwright/Puppeteer/Selenium/browser-use fallback; stop-report-ask on failure | Guard hook blocks installs and runs; deny rules block other browser MCPs and Claude in Chrome; failure procedure in agents and `CLAUDE.local.md` |
| P2 | Security built in from the start | §7; hooks active from the first commit |
| P3 | Status labels (UNVERIFIED/BLOCKED/FAILED) with evidence; never "done" because code was written | QA report format; §9 matrix |
| P4 | Web search/fetch allowed, but BrowserOS for most research (Mina, 12:36 PM) | `researcher.md` tool rules |

### 1d. Conflicts found and how they're resolved
| # | Conflict | Resolution |
|---|---|---|
| C1 | PDF: use BrowserOS "when available and relevant". Prompt: exclusive, no fallback | Follow the prompt. Browser work is BLOCKED when neo is down; nothing substitutes |
| C2 | The research agent suggested "Playwright MCP or Chrome DevTools MCP" as a fallback | **Rejected** (violates P1). Recorded here so nobody adds it later. |
| C3 | Guide says neo's MCP is at `127.0.0.1:9239/mcp` via `chrome://browseros/mcp` | Wrong for neo (that's core BrowserOS). neo's port varies (source default 9010; docs say 9200). Nothing hard-codes a port; the hook reads whatever URL Connect saved. |
| C4 | Prompt calls the PDF the hackathon spec | The hackathon spec is the Notion page + kickoff (`docs/hackathon.md`); both are applied |
| C5 | Agents/hooks in a shared repo would change Wali's and Michael's Claude Code too | Agents and hook wiring are **local to Mina** (`.claude/agents/local/`, `.claude/settings.local.json`, gitignored). Hook scripts are committed so teammates *can* opt in. |
| C6 | Hackathon 33B cap vs. BrowserOS's own built-in AI | BrowserOS is a **development tool only**, never in Clarity's runtime path. The README says so. |
| C7 | BrowserOS runs on Mina's Windows laptop; Clarity's Python runs on Brev | Run Claude Code on the laptop (where neo is). QA runs Python checks on Brev over `ssh`. A Claude Code session *on* Brev can't reach neo at 127.0.0.1 (by design). |
| C8 | Unit tests with jsdom (e.g. Vitest) aren't browser automation | Allowed if the dashboard ever needs them; real-browser checks go through BrowserOS only |

---

## 2. Prioritized implementation lineup

| # | Step | Why at this point | Depends on | Status |
|---|---|---|---|---|
| 1 | Commit the package (CLAUDE.md, contracts, docs, hook scripts) on Mina's branch; Mina's local config stays local | Everything else assumes it; hooks protect every later commit | — | Ready |
| 2 | Confirm BrowserOS neo connected (session-start status line says "reachable") | Highest-risk assumption; the guide says test it first | neo open | UNVERIFIED on Mina's laptop |
| 3 | 5-minute BrowserOS go/no-go (§5) | Proves the QA path before the dashboard depends on it | 2 | UNVERIFIED |
| 4 | Team confirms contracts v0.1 + bus owner (T1) | Unblocks parallel work; CP0 at ~1 PM | — | Open |
| 5 | Bus skeleton + client + `fake_scenario` | Teammates need it by CP1 (~2:30) | 4 | Not started |
| 6 | Dashboard skeleton on fake events (QA via BrowserOS) | Demo backbone; earliest visible progress | 3, 5 | Not started |
| 7 | Plan + film staged clips (3 simultaneous incidents) | Main open-data contribution; needed for real pipeline + eval | Team agreement on scenes (T6/T7) | Not started |
| 8 | Feeds replay + `cameras.json` + ground truth → Wali | Real pipeline input | 7 | Not started |
| 9 | Wire dashboard to the real pipeline; insurance recording before 8 PM | CP2/CP3 | 5–8 + teammates | Not started |
| 10 | README write-up + demo video + reviewer pass + final security check | Submission | all | Not started |

---

## 3. Skills and tools matrix

| Skill / tool | What it does | Use for | When | Output | Priority |
|---|---|---|---|---|---|
| BrowserOS neo (MCP) | Real browser driven by Claude Code: navigate, read, act, screenshot, console | Research; dashboard QA | Researcher and QA agents, automatically | Sourced findings; QA evidence | **Essential** |
| Hooks (`guard`, `session-start`) | Deterministic checks | Secrets, browser rule, session status | Every session / every Bash call | Block or status text | **Essential** |
| `frontend-design` skill | Typography/layout guidance for UI | Dashboard | When building dashboard UI | Polished, non-generic UI | Recommended |
| Grill Me (`/grill-me`, mattpocock-skills) | Relentless Q&A that challenges a plan, with recommended answers | Stress-testing this plan or a design | Optional, Mina-invoked, time-boxed to ~10 min | Settled decisions | Optional |
| Superpowers (obra/superpowers) | Full methodology: brainstorm → plan → TDD → subagent review; auto-triggers via a session hook | Its `systematic-debugging` and `verification-before-completion` ideas | If already installed | — | **Not recommended to install now**: always-on, mandatory workflows (brainstorming, strict TDD, worktrees, subagent-per-task) are too slow for a 24 h build and conflict with "don't overwhelm me". The two useful ideas are already in the loop. |
| gitleaks | Secret scanner | Extra layer in the guard hook | Automatic if installed | Block on finding | Optional |
| GitHub push protection | Server-side secret blocking | Last line of defense | Automatic on push | Push rejected | Essential (on by default for new public personal repos; Wali verifies) |
| WebSearch / WebFetch | Plain HTTP search and fetch | Quick one-fact lookups | Researcher, sparingly | — | Allowed (per Mina) |

---

## 4. Subagent architecture

All three are in `.claude/agents/local/` (Mina only). Claude picks them automatically from their descriptions. None can edit files, so the main session stays the single writer and decision-maker.

| Agent | Model | Mission | Inputs | Tools | Output | Done when | Depends on |
|---|---|---|---|---|---|---|---|
| **researcher** | Sonnet | Answer outside-the-repo questions with sources | A specific question | BrowserOS neo (primary), WebSearch/WebFetch (quick lookups); no edit/Bash | ≤300-word answer, tagged facts, sources with access method | Question answered or BLOCKED reported | BrowserOS reachable (else BLOCKED for browser parts) |
| **qa** | Sonnet | Prove the change works | What changed + where | Bash (build/test/validate, ssh to Brev), BrowserOS neo for the dashboard; no edits | PASS/FAIL/BLOCKED/PARTIAL with evidence | Every relevant check run or labeled UNVERIFIED | The change; dev server; Brev for Python |
| **reviewer** | Opus | Independent critique: rules, contracts, security, scope, demo risk; grill-style questions | Diff + requirements | Read, Grep, Glob, read-only Bash | SHIP / SHIP WITH FIXES / DON'T SHIP + must/should/nice list | All five check areas covered | QA passed first |

**Considered and not created:**
- **Requirements/architecture agent:** done once, in this doc and `docs/architecture.md`.
- **BrowserOS research, tech-stack, and community agents:** folded into `researcher`. One researcher with clear rules beats three overlapping ones.
- **Separate security agent:** folded into `reviewer` + the guard hook + deny rules.
- **"Grill me" agent:** the reviewer asks questions with recommended answers, and `/grill-me` exists if Mina wants it.

---

## 5. BrowserOS neo feasibility report

**Verdict: conditional GO.** Its tools cover every need. The connection must be confirmed on Mina's laptop (UNVERIFIED until the test below passes).

**What it is (VERIFIED, official docs + source, Oct 17):**
- A separate Chromium-based product from core BrowserOS, formerly "BrowserClaw".
- Repo: github.com/browseros-ai/BrowserOS (AGPL-3.0); last commit Oct 16, 2026.
- Windows x64 installer available.

**Connection (VERIFIED):**
- Streamable HTTP MCP on localhost, no token.
- Connect via the one-click **Connect** button in neo's MCP page. This writes a `browseros-neo` entry to `%USERPROFILE%\.claude.json` (user scope, outside the repo, as the guide wants). The manual equivalent is `claude mcp add --transport http browseros-neo <copied URL> --scope user`; use one method, not both.
- **The port is not fixed.** Source default for neo is 9010, the docs say 9200, and it shifts if busy. The guide's 9239 and `chrome://browseros/mcp` belong to core BrowserOS. Always use the copied URL.

**Tools (VERIFIED from source):** `tabs`, `navigate`, `snapshot`, `act` (click/type/fill/press/hover/select/scroll/drag), `read` (markdown/text/links/console), `grep`, `screenshot`, `evaluate` (JS), `run`, `wait`, `diff`, `pdf`, `download`, `upload`, `history`, `windows`, `tab_groups`, `browser_profiles`, `browser_target`. Covers navigate, read, click/type, console errors, screenshots, and localhost (no localhost block in code; UNVERIFIED in practice).

**Limitations and issues (VERIFIED from GitHub issues):**
| Issue | Impact | Mitigation |
|---|---|---|
| #2408 Win10 exits at launch with sandbox on (open) | neo may not start | Workaround: `--no-sandbox` launch flag |
| #2591 claw-server leaks sockets after days of uptime (open) | Instability on long runs | Restart neo every ~12 h; the session-start hook catches "not reachable" |
| #2424/#2706 MCP proxy binds 0.0.0.0 on Windows (app-level loopback check exists) | Possible LAN exposure | Keep "allow remote" off; answer the Windows firewall prompt with private-only/deny |
| #2763/#2866 MCP failed to start or unstable after update (closed) | Breaks after updates | Re-copy URL / click Connect after updates; hook detects |
| #2703 ~30 s cap per tool call | Long actions time out | QA keeps steps short |
| #2924 audit log stores typed values in plain text (open) | Secrets typed into pages leak locally | Never type secrets; no logins |
| All agents share one browser profile with real cookies | Logged-in sites exposed to agents | Use neo with no personal logins (or a fresh profile) |
| Telemetry on by default (anonymous PostHog) | Privacy | Turn off in Settings if desired |

**Community evidence:** no substantive Reddit, X, or HN reports found. Product Hunt comments and two blog posts are low credibility (vendor-adjacent or untested). GitHub issues are the only real field evidence (high credibility).

**Go/no-go test (5 minutes, Windows):**
1. Open BrowserOS neo. The MCP page shows Claude Code connected.
2. Start Claude Code in the repo. The session-start status must say **BrowserOS neo: reachable**.
3. `claude mcp list` shows the BrowserOS server as ✔ Connected. In Claude, `/mcp` lists `tabs`, `navigate`, `read`, `act`, `screenshot`.
4. With `npm run dev` running, ask: "Use the qa agent to open http://localhost:5173 in BrowserOS, read it, read the console, click the first button, take a screenshot."

5. Hook self-test (30 seconds): `node -v` works; `where bash` finds Git Bash; ask Claude to run `npm i playwright`. It must be refused with "BLOCKED by .claude/hooks/guard.mjs". If it isn't, the hooks aren't loaded (see Appendix B).

**GO** if all five steps pass. **NO-GO** on connection refused, a 403, missing tools, or a crash. In that case, follow the failure procedure: stop the browser task, report the exact error, classify it as configuration vs. limitation, and ask Mina. **No other browser tool.**

---

## 6. Research findings and sources (accessed Oct 17, 2026)

| Source | Kind | Used for | Credibility / access |
|---|---|---|---|
| docs.browseros.com/neo/mcp, /neo/mcp/manual, /neo/install, /neo/privacy, /neo/tabs-and-isolation | Official docs | Connection, privacy, isolation | High, full read |
| github.com/browseros-ai/BrowserOS (source at commit 7fdd50f, Oct 16; `skills/browseros-neo/SKILL.md`) | Repo | Port default, tool list, auth | High, read-only clone |
| BrowserOS GitHub issues #2408, #2424, #2591, #2703, #2706, #2763, #2866, #2924 | Issues | Known bugs | High, full read via API |
| docs.browseros.com/features/use-with-claude-code (core BrowserOS) | Official docs | Origin of the guide's 9239 port | High, full read |
| Product Hunt (neo, ~Aug 2026), notes.nicolasdeville.com (Oct 13), chatgate.ai (Aug 7) | Community | Anecdotes | Low |
| code.claude.com/docs/en/sub-agents, /hooks, /hooks-guide, /permissions, /mcp, /setup, /chrome, /skills, /memory, /best-practices | Official docs | Agent frontmatter, hooks (exit 2 blocks; Git Bash/PowerShell on Windows), deny rules, MCP scopes, CLAUDE.md size | High, read (some pages truncated at 100K chars) |
| github.com/obra/superpowers (v7.0.0, Oct 9) | Repo | Skill list, heavyweight workflows | High, cloned |
| github.com/mattpocock/skills (v1.3.1, Oct 9) | Repo | `/grill-me` behavior | High, cloned |
| docs.github.com (secret scanning, push protection), GitHub changelog 2024-03-11 | Official docs | Default protections on public repos | High |
| github.com/gitleaks/gitleaks (v8.30.1; `gitleaks git --pre-commit --redact --staged`) | Repo | Secret scanning command | High |
| docs.vllm.ai security + serve docs; vLLM source (`host` defaults to all interfaces) | Official | `--api-key` covers only some endpoints; bind 127.0.0.1 | High |
| vite.dev/guide/env-and-mode | Official | `VITE_*` vars ship to the browser | High |
| docs.nvidia.com/brev/latest/cli/connectivity | Official | `brev port-forward`; console tunnels are public | High |
| OWASP LLM01:2025; simonwillison.net "lethal trifecta" (2025-06-16) | Standard / expert blog | Prompt-injection risk of browsing agents | High / medium-high |
| humaninference.substack.com hackathon post (2026) | Community | "Feed tasks one at a time; heavy agent scaffolding drifted" | Medium |

Note: research for this document was done with this cloud session's web search/fetch, because BrowserOS neo runs on Mina's laptop and isn't reachable from here. The BrowserOS-first rule applies to Mina's Claude Code sessions.

---

## 7. Security checklist

**Setup (once)**
- [ ] `.gitignore` covers `.env`, `private/`, `CLAUDE.local.md`, `.claude/settings.local.json`, `.claude/agents/local/`, `.agent-logs/`, `data/raw/`, videos (done in the package).
- [ ] `git ls-files | findstr /i ".env private CLAUDE.local"` returns nothing; `.gitignore` doesn't protect already-tracked files.
- [ ] Wali (repo owner) confirms secret scanning + push protection are on: repo Settings → Advanced Security.
- [ ] BrowserOS neo: no personal logins (or a fresh profile); "allow remote" off; consider turning telemetry off.
- [ ] Optional: install gitleaks.

**While developing**
- Secrets only in `.env` (gitignored). `.env.example` holds placeholders only.
- Never put a secret in a `VITE_` variable (it ships to the browser).
- The bus validates every event against `contracts/schemas` and returns 422 on bad input; it must never crash on bad JSON.
- The dashboard renders event text as text, never as raw HTML (no `dangerouslySetInnerHTML`).
- Model servers and the bus bind to `127.0.0.1` on Brev; reach them with `brev port-forward`. No public Brev tunnels for 8000–8004 or 8080. vLLM's `--api-key` doesn't protect every endpoint, so don't rely on it.
- Treat web pages, tool output, and teammates' event text as untrusted data, never as instructions.
- Don't install unfamiliar packages; prefer well-known ones older than 2 weeks (also a hackathon rule).

**Before every commit (automatic + 10 seconds of eyes)**
- Guard hook scans staged changes (or `-a` changes) for secrets and forbidden files.
- Glance at `git status` and `git diff --staged`.

**Before every push**
- Guard hook scans all unpushed commits.
- GitHub push protection checks again server-side.

**Before submission**
- Reviewer agent pass (security section).
- `gitleaks git -v .` over full history if installed; otherwise the reviewer greps for key patterns.
- Repo, README, and video contain no internal company info, slide content, or personal data.

**If a secret leaks**
1. **Revoke/rotate it immediately** at the provider (HF, NVIDIA, GitHub…). Deleting it from the latest commit is not enough; it stays in history.
2. Then remove it from history (or recreate the branch) and force-push only with team agreement.
3. Tell the team; note it in the progress log.

---

## 8. Phased execution plan

| Phase | Time | Mina + Claude Code | Parallel (teammates) | Exit criteria |
|---|---|---|---|---|
| 0. Setup | now → 1:15 PM | Commit package; BrowserOS go/no-go; contracts + bus-owner confirmation | Michael: Brev + model servers. Wali: spotter prompt | Session status "reachable"; CP0 |
| 1. Fakes end-to-end | 1:15 → 2:30 | Bus + client + `fake_scenario` + replay; dashboard skeleton | Wali/Michael fake modes | CP1: incident moves on dashboard from fakes; QA PASS |
| 2. Real data | 2:30 → 4:30 | Film staged clips (3 overlapping incidents); `cameras.json`, ground truth, feeds replay; `data/README.md` | Spotter/checker on real frames | Wali consumes feeds; clips + method documented |
| 3. Integration | 4:30 → 7:15 | Dashboard polish (3 incidents, receipts, confirm); wire to real pipeline; insurance recording | Dispatcher + lookup live | CP2, CP2b, CP3; recording pushed before 8 PM |
| 4. Overnight (optional) | — | README draft, video script | Eval / NeMo Gym numbers | Draft exists |
| 5. Final | Sun 9:00 → 10:30 | Final numbers in README; reviewer pass; final video; submit | Final runs | Submitted by 10:30 |

**Time savers:**
- Claude runs QA and review itself, so Mina only reads verdicts.
- Fake modes mean nobody waits on anybody.
- The recorded run replays if anything breaks live.
- One small slice at a time; a community report says heavy parallel scaffolding drifted in a hackathon.

---

## 9. Testing and compliance matrix

| Requirement | Implementation | Verification | Status | Evidence |
|---|---|---|---|---|
| Contracts valid | `contracts/schemas` + `validate.py` | 7 examples pass; 5 bad examples rejected | **VERIFIED** | Run Oct 17 |
| Secrets never committed | `guard.mjs` + push protection | 23 test cases: secrets, .env, video, `commit -a`, chained `git add && commit`, `git add -f`, push of leaked commit blocked; clean commits and harmless commands mentioning browser tools allowed | **VERIFIED on Linux/Node 22**; UNVERIFIED on Windows | Test run Oct 17 |
| BrowserOS-only rule | `guard.mjs` + deny rules + agent rules | Playwright/Selenium installs blocked in test; deny rules load | Hook **VERIFIED**; deny rules UNVERIFIED until loaded on laptop | Test run Oct 17 |
| BrowserOS status each session | `session-start.mjs` | Not configured / not reachable / reachable all reported correctly | **VERIFIED in simulation**; UNVERIFIED with real neo | Test run Oct 17 |
| BrowserOS works for research + QA | researcher, qa | §5 go/no-go | UNVERIFIED | — |
| ≤ 33B generative params | Model table in `docs/architecture.md` (≈23.6B) | Reviewer checks; README table | VERIFIED on paper (model cards / listings) | Qwen3-VL-2B 2B; Nano 12B v2 VL 12.6B; Nano 9B v2 9B |
| Open data used + documented | Staged clips + method; licensed supplements | Reviewer; `data/README.md` complete | Not started | — |
| Code written during hack | Fresh repo, history from Oct 17 | `git log --reverse` | VERIFIED so far | First commit Oct 17 10:47 |
| Dashboard works | dashboard/ | qa: build + BrowserOS checks on fake and real events | Not started | — |
| Bus works | bus/ | qa: fake scenario → validate events.jsonl; bad event → 422 | Not started | — |
| Demo video 3–5 min | — | Duration check; Notion criteria | Not started | — |
| Submission on time | — | Form confirmation by 10:30 | Not started | — |

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation | Contingency (BrowserOS rule kept) |
|---|---|---|---|---|
| BrowserOS neo won't start or connect on Windows | Medium | High (no browser QA/research) | Go/no-go first thing; `--no-sandbox` workaround (#2408) | Browser tasks BLOCKED; non-browser QA (build, tests, contract validation) continues; ask Mina |
| neo port changes after restart/update | Medium | Medium | Hook detects "not reachable" every session | Click Connect again / re-copy URL |
| neo instability over long sessions (#2591) | Medium | Medium | Restart ~every 12 h | Same as above |
| Secret leaked | Low | High | Guard hook + push protection + reviewer | Rotate first, then clean history |
| Hooks fail on Windows (shell differences) | Low–Med | Medium | Node scripts, no `jq`, quoted `$CLAUDE_PROJECT_DIR`; Git Bash ships with Git for Windows | Fix shell setting (`CLAUDE_CODE_GIT_BASH_PATH`); hooks never block a session on their own failure except the guard |
| Bus ownership unresolved (T1) | Medium | High (dashboard has no feed) | Raise at CP0 | Dashboard runs on `bus.fake_scenario` + recorded runs |
| One GPU can't hold all models (T4) | Medium | High (team) | FP8 checkpoints | Michael's call; fake modes keep Mina unblocked |
| Staged "stabbing" unsafe / no open data | High | Medium | Demo fistfight + purse snatch (T7) | Keep stabbing as a label only |
| Overwhelm / context bloat | Medium | Medium | Agents absorb noise; short CLAUDE files; no Superpowers bootstrap | `/clear` between tasks; progress file carries state |
| Live demo breaks | Medium | High | Recorded `events.jsonl` + pre-recorded video | `bus.replay` |

---

## 11. Final readiness checklist (Sunday 10:00 AM)

- [ ] Session status said "BrowserOS neo: reachable" at least once, and the go/no-go passed (or browser checks are honestly marked BLOCKED in the README)
- [ ] QA PASS on bus, feeds, dashboard with real events; three incidents at once shown
- [ ] Reviewer verdict SHIP (or SHIP WITH FIXES, fixed)
- [ ] README: problem + user, architecture, model table ≈ 23.6B, data sources + licenses + staged-clip method, how to run, numbers, vLLM + NeMo Gym write-ups, "Claude Code and BrowserOS were dev tools only"
- [ ] No secrets: guard passed on final push; push protection quiet; `.env`/`private/`/`CLAUDE.local.md` untracked
- [ ] Demo video 3–5 min uploaded; link works in an incognito window
- [ ] Friction log finished ("finish friction log") and DM'd to @Robbie
- [ ] Form submitted by 10:30 AM; screenshot of confirmation saved

---

## Appendix A: files in this setup

| File | Shared or local | Purpose |
|---|---|---|
| `CLAUDE.md` | Shared | Project map, hard rules, contracts import |
| `CLAUDE.local.md` | Local (gitignored) | Mina's scope, the loop, BrowserOS rule, timeline |
| `.claude/rules/contracts.md`, `.claude/rules/dashboard.md` | Shared | Path-scoped rules |
| `.claude/hooks/guard.mjs`, `.claude/hooks/session-start.mjs` | Shared scripts (teammates can opt in) | The two hooks |
| `.claude/settings.local.json` | Local | Wires the hooks, allow list, and deny rules for Mina only |
| `.claude/agents/local/{researcher,qa,reviewer}.md` | Local | The three agents |
| `docs/progress/mina.md` | Shared | Session-to-session status |
| `docs/workspace-plan.md` | Shared | This document |

## Appendix B: hook wiring (already in `.claude/settings.local.json`)

- `SessionStart` → `node "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.mjs"` (15 s timeout; prints status into context).
- `PreToolUse` matcher `Bash|PowerShell` → `node "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.mjs"` (120 s; exit 2 blocks with a reason).
- Requires Node (installed) and, on Windows, Git Bash (ships with Git for Windows). If hooks error with a shell message, set `CLAUDE_CODE_GIT_BASH_PATH` to `C:\Program Files\Git\bin\bash.exe` in `.claude/settings.local.json` under `"env"`.
- A teammate who wants the same protection copies the `hooks` block into their own `.claude/settings.local.json`.
