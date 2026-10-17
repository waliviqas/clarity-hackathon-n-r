# Hackathon rules, judging, and submission

Source: the event's Notion page and kickoff talk (Oct 17, 2026). This is a summary for the team; when in doubt, the Notion page wins.

## Schedule

| When | What |
|---|---|
| Sat 11:00 AM | Hacking begins |
| Sat 12:30 PM / 6:00 PM | Lunch / dinner |
| **Sat 8:00 PM** | **Doors close** (no overnight onsite; Brev keeps running remotely) |
| Sun 9:00 AM | Doors reopen |
| **Sun 11:00 AM** | **Code freeze, submissions due. Late submissions are not accepted.** |
| Sun 11:15 AM | Judging |
| Sun 1:30 PM | Awards |

## Rules

- **Track:** must align with one track. Ours is **Multi-Agent Systems** (it also touches Tool-Calling, and Fine-Tuned only if we fine-tune the spotter): wire several small models so they coordinate (divide work, pass context, build on each other's output) to do something no single model could.
- **Parameter cap:** ≤ 33B total across all generative language models, including any used for verification, critique, routing, or speculative decoding. MoE = total params. Embedding and reranking models are excluded. Counted from the official model card.
- **Open data:** must meaningfully use open data. Public datasets and open-data APIs are fine. Synthetic data generated during the hack is fine **if we publish the data and the method**. We must reference our sources and show how open data is used.
- **Code:** everything required to run must be written during the hackathon. Open-source code only if it's been public for 2+ weeks.
- Tracks define *how* the AI works, not what problem it solves.

## Judging (100 points)

Philosophy: they judge **systems engineering**. A winner is a working system that ingests raw data, processes it, and produces a valuable result. Not a deck, not a thin API wrapper.

1. **Technical Execution & Completeness:** runs end-to-end without major failures; uses open data; real engineering underneath. Multi-agent specifically: do several small models genuinely divide the work and exchange information to do something beyond one model?
2. **NVIDIA & Red Hat Ecosystem Utility:** is their tech central (not bolted on for eligibility)? Can we explain *why* we chose it (speed, local inference, privacy, scale, deployment)? How deeply is it integrated?
3. **Value & Impact:** a real, clearly defined, well-scoped problem (vague framing scores low). Could a real user act on it tomorrow?
4. **Innovation & Execution:** novel combination of data, models, or modalities; optimized for speed or scale.

**Implication: bring measured numbers** in every category (latency, throughput, accuracy vs. a single-model baseline).

## Bounties (on top of the track prize)

| Bounty | Required | Submit |
|---|---|---|
| Best Use of Nemotron Lightning | Lightning is a core part of the project | **Not pursued:** Lightning (30B) doesn't fit beside our spotter + checker + dispatcher. Revisit only if the model plan changes. |
| **Best Use of Red Hat vLLM** | vLLM is the serving layer for a core model, central to how the app runs | How vLLM fits the architecture, how we configured and optimized it, measurable results. Depth over breadth. |
| **Best Model Improvement with NeMo Gym** | A NeMo Gym environment with tasks, tools the agent can use, and code that scores each attempt | Gym setup, baseline vs. final scores on the same held-out tasks and config, how to run scoring, what changes caused the gain |
| NVIDIA Champions Choice | Judges' favorite | A polished demo and clear story |
| Friction log ($25 Brev credits, first 20) | Each person runs `tools/friction-log.txt` with their coding agent | DM the report to @Robbie on Discord |

Track winners each get an RTX 5090, swag, and All Things Open passes.

## Submission (Airtable form, linked from the Notion page)

- [ ] Link to the **public GitHub repo**
- [ ] **Project description**
- [ ] **3–5 minute demo video.** Exact criteria are on the Notion "Demo Video Instructions" page (needs a browser). Record early; submitting takes 10–15 minutes.
- [ ] README includes: problem + user, architecture diagram, track fit, **model + parameter table proving ≤ 33B (currently ≈ 23.6B)**, data sources + licenses (+ synthetic data method), how to run, results/numbers, the three bounty write-ups, and a note that Claude Code was a development tool only (not part of the runtime).

## Demo video outline (~4 min; adjust to the Notion criteria)

1. **0:00–0:30** The problem and the user: a security operator watching many cameras can't follow one person across them in real time.
2. **0:30–1:00** Architecture + parameter budget + data sources.
3. **1:00–2:45** Live run: incident detected → camera agents hand the person off → path builds on the map → dispatcher recommends → operator confirms. Show the receipts trail.
4. **2:45–3:30** Numbers: three incidents at once on vLLM (latency/throughput), spotter vs. spotter+checker precision, NeMo Gym baseline vs. final, multi-agent vs. single-model.
5. **3:30–4:00** Why small specialized models + vLLM + NeMo Gym; runs on an agency's own hardware; what's next.

## Links

- Hackathon Notion: https://concrete-panther-c83.notion.site/nv-rh-small-models-hack
- Discord: `#small-models-hack-raleigh` on the NVIDIA Developer server
- Brev docs: https://docs.nvidia.com/brev/getting-started/overview
- Brev CLI connectivity (ssh, port-forward): https://docs.nvidia.com/brev/latest/cli/connectivity
- vLLM recipe, Nemotron Nano 9B v2: https://recipes.vllm.ai/nvidia/NVIDIA-Nemotron-Nano-9B-v2
- vLLM recipe, Nemotron Nano 12B v2 VL: https://docs.vllm.ai/projects/recipes/en/latest/NVIDIA/Nemotron-Nano-12B-v2-VL.html
- vLLM security (what `--api-key` does and doesn't protect): https://docs.vllm.ai/en/latest/usage/security.html
- NeMo Gym: https://github.com/NVIDIA-NeMo/gym and https://docs.nvidia.com/nemo/gym/about/
