# Clarity contracts (v0.1)

This folder is the **single source of truth** for every message passed between the three parts of Clarity.
If your code and this folder disagree, this folder wins until the team agrees to change it.

- `schemas/*.schema.json`: JSON Schema (draft 2020-12) for each message. Validate against these.
- `examples/*.json`: one valid example of each message. Use them as fixtures and for fake producers.
- `CHANGELOG.md`: every change, who agreed, and when.

Status: **v0.1, agreed in chat Sat Oct 17 ~noon** (Mina proposed; Wali's changes folded in). Michael has not reviewed `dispatch` yet.

---

## Who sends what

```
 feeds (Mina) ──FramePacket (Python)──► perception (Wali) ──detection──► camera agents (Wali)
      │                                                                     │      ▲
      └──camera_status──┐                                         relay ────┘      │ relay
                        ▼                                    agent_verdict         │
               ┌──────────────────┐ ◄──────────── all events are published ───────┘
               │   bus (Mina)     │                    │
               │ POST /events     │ ◄── dispatch ── dispatcher (Michael) ◄── agent_verdict
               │ WS   /ws         │                    ▲   uses graph.predict_next (Wali)
               └──────────────────┘                    │
                 │            ▲                         │
                 ▼            └── operator_action ──────┘ (dispatcher polls GET /events)
            dashboard (Mina)
```

| Message | Schema | Producer | Consumers |
|---|---|---|---|
| Camera config (`cameras.json`) | `cameras` | Mina (data) | Wali (graph), Mina (dashboard, feeds), Michael |
| Frame | Python only, see below | Mina (feeds) | Wali (perception) |
| `detection` | `detection` | Wali (perception) | Wali (agents), bus → dashboard |
| `relay` | `relay` | Wali (agents) | Wali (agents), bus → dashboard |
| `agent_verdict` | `agent_verdict` | Wali (agents) | Michael (dispatcher), bus → dashboard |
| `dispatch` | `dispatch` | Michael (dispatcher) | bus → dashboard |
| `operator_action` | `operator_action` | Mina (dashboard) | Michael (dispatcher) |
| `camera_status` | `camera_status` | Mina (feeds) | bus → dashboard |

---

## Rules for every message

1. **snake_case** field names.
2. Every runtime event has `type`, `schema_version` (`"0.1"`), `event_id`, `ts`. Optional: `run_id`, `source`.
3. **IDs are prefixed strings**: `cam_03`, `det_…`, `rel_…`, `ver_…`, `dsp_…`, `op_…`, `cst_…`, `subj_…`, `inc_…`.
4. **`ts` is seconds as a number on the run clock.** Replay: the video's own timeline, so all cameras line up. Live: unix epoch seconds.
5. **Decisions cite `evidence_event_ids`.** That's the receipts trail the dashboard shows.
6. **Enums are closed.** `activity`: `stabbing | fistfight | purse_snatch | none`. `direction`: `north | northeast | east | southeast | south | southwest | west | northwest | unknown` (or `null` where allowed).
7. Extra fields are allowed (`additionalProperties: true`), so you can add a field without breaking others. **Renaming or removing a field is a breaking change** (see "Changing a contract").

---

## Interfaces that aren't JSON

### Frame (Mina → Wali), Python
```python
# feeds/base.py  (owner: Mina)
@dataclass
class FramePacket:
    camera_id: str          # "cam_03"
    ts: float               # run-clock seconds
    frame_idx: int
    source_kind: str        # "replay" | "live"
    image: np.ndarray       # H x W x 3, BGR, uint8 (OpenCV default)

def open_feeds(cameras_json: str, fps: float = 1.0, speed: float = 1.0) -> Iterator[FramePacket]:
    """Yields frames from all cameras interleaved in ts order. Wali samples ~1 fps."""

class FrameBuffer:
    """Keeps the last N frames per camera, because the VLM needs motion (several frames)."""
    def push(self, pkt: FramePacket) -> None: ...
    def last_n(self, camera_id: str, n: int) -> list[FramePacket]: ...
```

### Graph prediction (Wali → Michael), Python
```python
# graph/  (owner: Wali)
def predict_next(camera_id: str, direction: str | None) -> list[dict]:
    """Returns [{"camera_id": "cam_08", "probability": 0.7}, ...], sorted by probability, descending.
    Michael copies this into dispatch.predicted_next."""
```

### Bus (everyone → Mina's event server)
```python
# bus/client.py  (owner: Mina)
from bus.client import publish, fetch

publish(event: dict) -> None
    # POST to {CLARITY_BUS_URL}/events. Times out fast and never crashes the caller.
fetch(type: str, since_ts: float = 0) -> list[dict]
    # GET {CLARITY_BUS_URL}/events?type=...&since_ts=...  (Michael uses this to read operator_action)
```

| Endpoint | Purpose |
|---|---|
| `POST /events` | Publish one event. Validated against `schemas/`; invalid → HTTP 422 with the error (set `CLARITY_BUS_STRICT=0` to accept with a warning instead). |
| `GET /events?type=&since_ts=` | Read past events (polling). |
| `WS /ws` | Dashboard stream. First message is a `bus_snapshot` (cameras + recent events), then one event per message. |
| `GET /cameras` | The active `cameras.json`. |
| `GET /health` | Liveness + counts of valid/invalid events. |

Every accepted event is appended to `runs/<run_id>/events.jsonl`, so any run can be replayed into the dashboard later (demo insurance).

Default: `CLARITY_BUS_URL=http://localhost:8080` (everything Python runs on the Brev box).

---

## Changing a contract

1. Propose the change in the team chat: field, old, new, why.
2. All three agree (a 👍 is enough).
3. Edit the schema + example in **one** commit, bump `schema_version` for breaking changes, add a `CHANGELOG.md` line.
4. Tell the team to pull. Producers and consumers update in the same hour.

Never "just change it" in your own code. That's how the map goes blank on Sunday morning.
