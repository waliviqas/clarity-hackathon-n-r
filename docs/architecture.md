# Architecture

Status: v0.2, Sat Oct 17 ~12:45 PM (model plan updated from the team wiki). Subject to change; update this file when the design changes.

## The pitch in one paragraph

A security operator watches dozens of cameras and can't follow one suspect across them in real time. Clarity puts a small agent beside every camera. When a camera spots a crime, its agent describes the suspect in words and passes that description to the neighbor cameras they're likely heading toward. Those agents confirm or reject the match and pass it on. A dispatcher agent coordinates the response. **The system recommends; a human confirms.** No face recognition: matching uses clothing/build descriptions. It's designed to run on an agency's own hardware, so **video never leaves the building**. In the demo, phones and clips are the lenses, and the Brev GPU box plays the "chip beside each camera."

Why many small models: one big model can't watch every camera continuously, fast and cheaply. Small specialized models doing small, checkable judgments can, and each judgment leaves a receipt the operator can audit.

## Components

| Component | Owner | Tech | Input → output |
|---|---|---|---|
| Camera feeds | Mina | Python, OpenCV | Staged clips / dataset clips replayed as live cameras, or phone video → `FramePacket` |
| Staged clips + open data | Mina | Phones, licensed datasets | Clips, `cameras.json`, ground truth, published method |
| **Spotter** | Wali | Qwen3-VL-2B on vLLM (fine-tune optional) | Last few frames (~1 fps) → `detection` (activity, appearance text, direction) |
| **Checker** | Wali | Nemotron Nano 12B v2 VL on vLLM | Confirms or rejects what the spotter flagged (second opinion on the frames) |
| Context relay | Wali | Python (an inbox per camera agent) | `detection` / incoming `relay` → `agent_verdict`, new `relay` |
| Camera graph | Wali | NetworkX | `cameras.json` → graph, `predict_next(camera_id, direction)` |
| **Dispatcher** | Michael | Nemotron Nano 9B v2 on vLLM | `agent_verdict` stream + `predict_next` + lookup results → `dispatch` |
| **Lookup (RAG)** | Michael | Nemotron Embed + Rerank | Dispatcher query → relevant reference passages (source TBD) |
| GPU server | Michael | NVIDIA Brev, vLLM | Hosts all model servers and all Python |
| Testing | Michael | NVIDIA NeMo Gym | Tasks from ground truth → scores, baseline vs. final |
| Dashboard | Mina | React + TypeScript + Vite + Leaflet | Bus WebSocket → map, incident panel, receipts log; sends `operator_action` |
| Event bus | Mina (pending confirmation) | Python (FastAPI + WebSocket) | Every event in → validated, logged, streamed to the dashboard |
| Demo video + write-up | Mina | — | README, video |

## Data flow

```
staged / dataset clips ─► feeds ─FramePacket─► spotter (Qwen3-VL-2B) ─flag─► checker (Nano 12B v2 VL) ─detection─► camera agent inbox (cam_A)
                            │                                                                                          │ relay to likely next cameras
                            │                                                                                          ▼
                            │                                                                         camera agent inbox (cam_B) ─agent_verdict─► dispatcher (Nano 9B v2)
                            │                                                                                                                       │ ▲ lookup (Embed+Rerank)
                            ▼                                                                                                                       ▼ │ predict_next (graph)
                           bus ◄──────────────────────────────── every event is published here ─────────────────────────────────────────────── dispatch
                            │ WebSocket
                            ▼
                        dashboard ── operator_action ──► bus ──► dispatcher
```

Where exactly the checker sits (confirming the spotter's flag, matching people at the next camera, or both) is Wali's call; see `docs/open-questions.md`.

## Model budget (must stay ≤ 33B combined; keep this table current)

| Model | Role | Total params | Counts? | Served by |
|---|---|---|---|---|
| Qwen3-VL-2B (base or fine-tuned) | Spotter | 2B (model card) | Yes | vLLM :8001 |
| Nemotron Nano 12B v2 VL | Checker | 12.6B (published listings; the "12B" name rounds down) | Yes | vLLM :8002 |
| Nemotron Nano 9B v2 | Dispatcher | 9B (model card) | Yes | vLLM :8000 |
| Nemotron Embed | Lookup retrieval | — | **No** (embedding model) | :8003 |
| Nemotron Rerank | Lookup ranking | — | **No** (reranker) | :8004 |
| **Total generative** | | **≈ 23.6B** (≈ 9.4B headroom) | | |

Serving all of this on one GPU is tight in BF16 (roughly 45–50 GB of weights before KV cache). FP8 checkpoints exist for the 9B and 12B VL models; Michael decides the precision and memory split.

## Where we use a model vs. plain code

| Task | Approach | Why |
|---|---|---|
| Decoding video, sampling frames, timing | Code | Exact and cheap |
| "Is something happening in these frames? Who, which way?" | Spotter (2B VLM) | Cheap enough to run on every camera continuously |
| "Is the spotter right?" | Checker (12.6B VLM) | Runs only on flagged moments, so the bigger model's cost is paid rarely |
| Which camera is next, travel-time windows | Code (graph) | Geometry, not language |
| "What should the operator do?" | Dispatcher (9B LLM) + lookup | Summarize evidence into a recommendation grounded in reference text |
| Validation, scoring, metrics | Code | Must be exact |

The spotter → checker cascade is the core small-model story: a tiny model screens everything, and a bigger one confirms only what matters.

## Design principles

- **Small, checkable judgments.** Each model call gets a small slice of context and returns a schema-constrained decision.
- **Receipts.** Every decision cites the `event_id`s it's based on, and the dashboard shows that chain. An operator can see *why* the system thinks the person went north.
- **The graph is the shared map.** Agents only talk about cameras that are neighbors in `cameras.json`.
- **Deterministic glue.** Orchestration, timing, and fallbacks are plain Python, not an agent framework.
- **Fail soft.** If a model call fails or returns bad JSON, retry once, then fall back to a rule (for example, "no match") and mark the receipt as a fallback. The pipeline keeps running.
- **Parallel by design.** Three simultaneous incidents in the demo show vLLM batching requests from many cameras at once.

## Evaluation plan (Michael owns; numbers go in the README)

- **Tasks:** scenarios built from ground truth: a suspect appears at camera A, then B, then C.
- **Systems compared:**
  - **Baseline:** one model sees all cameras' raw detections and must reconstruct the path.
  - **Clarity:** the relay network.
- **Metrics:**
  - path accuracy (correct next camera; full path exact-match)
  - detection precision/recall per crime type (spotter alone vs. spotter + checker)
  - time-to-alert at each camera
  - model calls and tokens per incident
  - vLLM throughput and p50/p95 latency with three incidents running at once
- **Fine-tune (optional):** if the spotter is fine-tuned, report before/after on test clips that were never used for training.
- **NeMo Gym bounty:** wrap the same tasks + a scoring function as a Gym environment. Report baseline vs. final on held-out scenarios and isolate which change caused the gain.
