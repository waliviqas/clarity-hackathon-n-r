# Handoff to Wali (Sat Oct 17, ~7:40 PM): training clips + how to plug into the pipeline

**1. Training clips (11 files, ~100 MB, sent by Mina).** List with labels and licenses: `data/training/staged_clips.csv`; sources and shortfalls: `data/training/SOURCES.md`.
- Labels come from the datasets and are **not yet verified frame by frame** (Mina's side verifies tonight).
- Mix: **4 fistfight, 1 purse_snatch, 6 none, 0 stabbing.** Suggested split: 8 train, 3 validation (Fight_RunAway2, Walk2, ex050).
- **Our Annex staged clips are TEST ONLY.** Never train on them (hackathon rule: separate train/test, report before/after on the test clips).
- 8 are **CAVIAR**, CC BY-SA. Credit: "EC Funded CAVIAR project/IST 2001 37540, http://homepages.inf.ed.ac.uk/rbf/CAVIAR/". Anything derived from them stays BY-SA.
- CAVIAR ground-truth XML tags every frame (25 fps), including `situation=fighting`. That gives exact fight windows, e.g. Fight_Chase frames 297–366 ≈ 11.9–14.6 s.
- The 3 `ex0xx` clips are **MEVA**, CC BY 4.0 (credit MEVA, mevadata.org). The theft clip (ex085) still needs a check that it's a grab from a person, not an unattended bag.

**2. What the spotter sees live (match training to this).** `open_feeds` gives BGR uint8 numpy frames, about 1 frame per second per camera, at most 960 px wide (default `max_width`), from 720p / 10 fps H.264 clips. CAVIAR is 384×288, so resize consistently.

**3. Plug in (branch `Mina`):**
```python
from feeds.base import open_feeds, FrameBuffer
from bus.client import publish

buf = FrameBuffer(n=8)
for pkt in open_feeds("data/sites/annex/cameras.json", fps=1.0, publish_status=True, drop_late=True):
    buf.push(pkt)
    frames = buf.last_n(pkt.camera_id, 4)   # oldest → newest, for the VLM
    # spotter → checker → publish(detection)
```
- Read frames in one thread with per-camera queues, so model calls don't stall the feed. `drop_late` keeps it real-time.
- `publish()` every `detection`, `relay` and `agent_verdict`. The bus validates each one and returns 422 with the reason if something's wrong; it never crashes your code.
- **detection** required fields: `type, schema_version "0.1", event_id det_…, ts (= pkt.ts, run clock), camera_id, track_id, confidence, activity (stabbing|fistfight|purse_snatch|none), appearance (clothing words), direction (8 compass points | unknown)`.
- **relay**: `event_id rel_…, ts, from_camera, to_camera, subject_id subj_…, summary, appearance, direction, confidence, evidence_event_ids` (+ optional `activity`, `expected_arrival_s`).
- **agent_verdict**: `event_id ver_…, ts, agent_id, camera_id, subject_id, decision (match|no_match|uncertain), confidence, reason, evidence_event_ids`.
- Check files with `python contracts/validate.py <file>`. Examples are in `contracts/examples/`, and a full scripted run is `python -m bus.fake_scenario --out x.jsonl`.
- `travel_time_s` in cameras.json can be 0 when two views overlap.
- Camera names are neutral on purpose (no "decoy" or role words), so don't put roles in prompts.

**4. Asks (tonight):**
1. Push your branch (even work in progress) so we can test it against the bus.
2. Be connected to the bus by about **11 PM**.
3. Fine-tune: yes or no?
4. What input your model expects (resolution, frames per call), so the clips match.
5. Post your written consent to publishing the staged clips (CC BY 4.0) in the team chat.
