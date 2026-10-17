# Dispatcher (#5)

Turns detections into dispatch decisions. Rules handle the clear cases; a small model served on vLLM handles only the ambiguous ones; every model answer is checked against the evidence before it can send police.

```
Events (#2) ─► group into incidents (time window + camera-graph distance)
                    │
                    ▼
                  gate ──clear dispatch / clear dismiss──► template decision   (no model call)
                    │
                    └─ambiguous──► model (vLLM, JSON schema) ─► verifier ──ok──► decision
                                        ▲                          │
                                        └──── errors, 1 retry ─────┘
                                                                   └─still bad──► "monitor" + needs_review
```

## Input contract (from crime detection, #2)

`Event(event_id, camera_id, timestamp, label, confidence, description="")`

- `timestamp`: unix seconds
- `label`: one of the keys in `rules.SEVERITY` (unknown labels get severity 2)
- `description`: optional caption; the model sees it, rules don't

Camera graph: `CameraGraph(cameras, edges)` or `CameraGraph.from_networkx(g)` (edge attr `weight`, node attr `name`).

## Output contract (to dashboard, #6)

`DispatchDecision.to_dict()`:

| field | meaning |
|---|---|
| `decision` | `dispatch` / `monitor` / `dismiss` |
| `priority` | 1–5 |
| `incident_type`, `location_camera_id`, `location_name`, `summary` | what and where |
| `cited_event_ids` | evidence for the decision (always resolvable) |
| `route` | `rules`, `model`, or `fallback` |
| `needs_review` | true when the model failed verification or was unavailable |
| `station_id` | nearest station by graph distance (dispatch only) |
| `model_calls`, `latency_ms` | for metrics |

## Safety properties

- A model answer that cites events that don't exist, names a camera outside the incident, claims a type no cited event supports, or inflates priority is rejected.
- Unverified or failed model calls never dispatch; they become `monitor` + `needs_review`.
- High-severity labels are never auto-dismissed by rules.

## Running

```bash
pip install -r requirements.txt
python -m pytest -q
python -m dispatcher.demo                     # scripted model, no GPU

export CLARITY_LLM_BASE_URL=http://<brev-host>:8000/v1
export CLARITY_LLM_MODEL=<served-model-name>
python -m dispatcher.demo --live              # real model on vLLM
```

The system prompt is constant and all per-incident data goes in the user message, so vLLM's `--enable-prefix-caching` reuses the prompt across calls.
