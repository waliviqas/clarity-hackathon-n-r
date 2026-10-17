# Dispatcher (#5)

Consumes the team's **schema v0.1** messages and emits `dispatch` messages for the dashboard. Rules handle clear cases; a small model served on vLLM handles only the ambiguous ones; every model answer is checked against the evidence before it is emitted.

```
detection / relay / agent_verdict ─► per-subject case (keyed by subject_id)
                                          │
                                          ▼
                     path + predicted_next (deterministic, from cameras.json)
                                          │
                                        gate ──no activity / trivial──► nothing emitted
                                          │
                                          ├──clear (e.g. weapon ≥0.85, no uncertain verdicts)──► template dispatch (no model)
                                          │
                                          └──ambiguous──► model (vLLM, JSON schema) ─► verifier ──ok──► dispatch
                                                               ▲                          │
                                                               └──── errors, 1 retry ─────┘
                                                                                          └─still bad──► status "tracking", "Operator review needed."
operator_action ─► confirm: status "alert", requires_human_confirm false · dismiss: status "resolved", incident goes quiet
```

## Messages

| Direction | type | What the dispatcher uses |
|---|---|---|
| in | `detection` | `camera_id`, `activity`, `activity_confidence` (attached to a subject once a relay/verdict cites it) |
| in | `relay` | `subject_id`, `from_camera`, `to_camera`, `summary`, `evidence_event_ids` |
| in | `agent_verdict` | `subject_id`, `camera_id`, `decision`, `reason`, `evidence_event_ids` |
| in | `operator_action` | `incident_id`, `action` |
| out | `dispatch` | exactly the v0.1 fields |

Messages with a missing header field or a `schema_version` other than `0.1` are rejected (counted in `stats["rejected"]`).

### How `dispatch` fields are filled

| field | source |
|---|---|
| `incident_id` | `inc_N`, one per subject, assigned when the subject first needs a dispatch |
| `path` | relay origin cameras (at the cited detection's ts) + cameras with a `match` verdict, earliest ts per camera |
| `predicted_next` | unvisited neighbors of the last path camera from `cameras.json`; a camera already relayed to but not yet answered gets 3× weight |
| `status`, `priority`, `recommendation`, `reason`, `evidence_event_ids` | rules template (clear cases) or the model (ambiguous), always verified |
| `requires_human_confirm` | `true` until an `operator_action` arrives |
| `ts` | latest `ts` seen on the shared clock (not wall time) |

A new dispatch is only emitted when its content changes, so the dashboard isn't spammed.

## Severity (keyed on `detection.activity`)

`weapon`/`shooting` 5 · `assault`/`fight`/`abandon_package`/`vehicle_crash`/`fire` 4 · `break_in`/`theft`/`fall` 3 · `vandalism`/`trespass` 2 · `loitering` 1 · unknown 2 · `null` 0.
→ priority: ≥4 high, 3 medium, else low. **The activity vocabulary must match the detector's.**

## Safety properties

- The model can't cite events that aren't in the subject's evidence, mention cameras outside the case, set a priority above what the cited activities support, or raise an `alert` without a medium+ severity activity.
- Unverified or failed model calls never raise an alert; they stay `tracking` with "Operator review needed."
- High-severity activities are never auto-ignored by rules.
- A human confirms every recommendation (`requires_human_confirm`).

## Metrics

`Dispatcher.audit` has one row per emitted dispatch: `route` (`rules` / `model` / `fallback` / `operator`), `model_calls`, `verifier_errors`, `latency_ms`. `Dispatcher.stats` has the totals.

## Running

```bash
pip install -r requirements.txt
python -m pytest -q
python -m dispatcher.demo                                  # built-in scenario, scripted model, no GPU
python -m dispatcher.demo --cameras cameras.json --messages run.jsonl   # replay real messages

export CLARITY_LLM_BASE_URL=http://<brev-host>:8000/v1
export CLARITY_LLM_MODEL=<served-model-name>
python -m dispatcher.demo --live
```

The system prompt is constant and all per-case data goes in the user message, so vLLM's `--enable-prefix-caching` reuses the prompt across calls.
