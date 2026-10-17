# Clarity: project guide for Claude Code

Clarity is a network of small AI agents, one beside each security camera. When a camera spots a crime (stabbing, fistfight, purse snatch), its agent describes the suspect in words and passes that description from camera to camera along their likely path. A dispatcher agent coordinates the response, and a human operator confirms or dismisses it on a map. **Pitch:** it runs on a police agency's own hardware, so video never leaves the building.

Built for the **NVIDIA x Red Hat Small Models Hack** (Raleigh, Oct 17–18, 2026). Main track: **Multi-Agent Systems** ("many small models beating one big one").

**Code freeze: Sunday Oct 18, 11:00 AM ET. Team target: submit by 10:30 AM.** Doors close 8 PM Saturday and reopen 9 AM Sunday.

Everything here is v0 and subject to change. When something in this file is wrong, fix the file (with the team's OK) rather than working around it. The team's wiki page "Clarity NVIDIA Hack" holds the latest team decisions; if it disagrees with this file, ask the user which is current.

## Team and ownership

| Person | Owns | Folders |
|---|---|---|
| **Mina** | Camera feeds, staged clips + open data, dashboard, demo video + write-up (README) | `feeds/`, `data/`, `dashboard/`, `bus/` (bus owner pending confirmation) |
| **Wali** | Crime detection (spotter + checker), camera graph (NetworkX), context relay (an inbox per agent) | `perception/`, `agents/`, `graph/` |
| **Michael** | Brev + vLLM serving, dispatcher, lookup (RAG), NeMo Gym | `infra/`, `dispatcher/`, `lookup/`, `eval/` |
| Shared | Contracts, docs, README | `contracts/`, `docs/`, `README.md` |

- **Only edit folders owned by the person you're working for.** Read anyone's code freely. If another part needs a change, write down exactly what and why, and tell the user to ask its owner.
- Each person works on their own branch and merges to `main` at the integration checkpoints in `docs/integration.md`.

## Hard rules (breaking these can disqualify us)

1. **≤ 33B parameters total, combined across all generative language models**, counted from each official model card. MoE models count *total* params, not active. Verifiers, routers, critics, and speculative-decoding draft models all count. Embedding and reranking models don't.
   - Current plan ≈ **23.6B**: Qwen3-VL-2B (2B) + Nemotron Nano 12B v2 VL (12.6B) + Nemotron Nano 9B v2 (9B). Nemotron Embed + Rerank are excluded.
   - That leaves ~9B of headroom. Adding or swapping any model means updating the budget table in `docs/architecture.md` first.
   - Nemotron 3.5 Lightning (30B) is **not** in the plan; it doesn't fit alongside the others.
2. **All code must be written during the hackathon.** Open-source libraries are fine only if they've been public for 2+ weeks. Never copy code from earlier projects.
3. **Open data is required.** Every dataset goes in `data/README.md` with source, license, and how we use it. Our own staged clips count only if we **publish the clips and the method**. Credit licenses that require attribution (e.g. MEVA is CC BY 4.0; OpenStreetMap is ODbL).
4. **Nothing sensitive is ever committed or pushed.** That means:
   - secrets: API keys, tokens, passwords, private keys, `.env` files
   - personal data, and faces of people who didn't consent
   - anything in `private/`, `CLAUDE.local.md`, or `.agent-logs/`
   - raw video or large data (`data/raw/`)
   - hackathon slide content, or any company's internal information

   Before every commit and push, check `git status` and the staged diff. If a secret was ever committed, rotate it first; deleting it later doesn't remove it from history.
5. **Footage of people:** only public-dataset actors and consenting teammates. No real weapons or knife props when staging scenes.
6. **If the Qwen spotter is fine-tuned:** training and test clips must be separate, and the README shows a before/after table on the test clips.

## Contracts

All messages between parts follow `contracts/`. Imported below so every session sees them:

@contracts/README.md

- Never rename or remove a field on your own; propose it to the team (process at the end of `contracts/README.md`).
- Validate before merging: `python contracts/validate.py <files>`.
- Every part must run alone against fake inputs built from `contracts/examples/`.

## Runtime layout (ports are proposals; Michael owns serving)

| Where | What | Port |
|---|---|---|
| Brev GPU box | vLLM: Nemotron Nano 9B v2 (dispatcher) | 8000 |
| Brev GPU box | vLLM: Qwen3-VL-2B (spotter) | 8001 |
| Brev GPU box | vLLM: Nemotron Nano 12B v2 VL (checker) | 8002 |
| Brev GPU box | Nemotron Embed / Rerank (lookup) | 8003 / 8004 |
| Brev GPU box | Bus (event server for the dashboard) | 8080 |
| Brev GPU box | feeds → spotter → checker/agents → dispatcher (Python) | — |
| Mina's laptop (Windows) | Dashboard (Vite dev server), reaches the bus via `brev port-forward` | 5173 |

All Python runs on the Brev box. The demo shows **three crimes at once** to prove vLLM serves them in parallel. Settings come from environment variables (see `.env.example`); never hard-code hosts, ports, or keys.

## Conventions

- **Python 3.10+.** Run from the repo root as modules (`python -m feeds.replay`), so `from contracts…` / `from bus.client import publish` imports work. Each top-level folder keeps its own `requirements.txt`.
- **Paths may contain spaces** (one teammate's clone is in `~/hackathons/nvidia x red hat/`). Always quote paths in scripts and commands.
- **Model calls** go through the OpenAI-compatible client pointed at our vLLM servers. Use structured outputs (`response_format` with a JSON schema) and temperature 0 for agent decisions. Never put a hosted or closed model in the runtime path; hosted endpoints are for dev only.
- **Use plain code, not a model, for anything deterministic:** parsing, timing, graph math, validation, scoring.
- Publish every contract event to the bus, even internal ones (relays, verdicts). That's what makes the receipts trail visible.
- Keep commits small and messages clear. Don't force-push shared branches.

## Docs (read when relevant)

- `docs/hackathon.md`: rules, judging rubric, bounties, submission checklist, demo-video outline.
- `docs/architecture.md`: components, data flow, model budget, design principles, evaluation plan.
- `docs/integration.md`: ports, env vars, start order, fake modes, checkpoints, demo fallback.
- `docs/open-questions.md`: undecided items and who decides them. Check before assuming.
- `data/README.md`: datasets, licenses, attribution, staged clips, ground truth.

## Don't

- Don't change `contracts/` without the team's agreement.
- Don't add a model without updating the parameter budget.
- Don't add new frameworks or services when plain Python does the job.
- Don't commit data, videos, secrets, or `private/`.
- Don't push, open PRs, or post anywhere unless the user asks.
