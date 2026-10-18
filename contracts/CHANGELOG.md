# Contracts changelog

## v0.1 (Sat Oct 17, ~12:00)
- Initial set: `cameras`, `detection`, `relay`, `agent_verdict`, `dispatch`, `operator_action`, `camera_status`, plus the Python `FramePacket`, `predict_next`, and bus client interfaces.
- Wali's changes folded in:
  - `cameras.neighbors[].direction` added (graph predicts the next camera from it).
  - `detection.appearance_id` replaced by `appearance` (text from the VLM); `direction` added; `bbox` nullable; `track_id` is one per detection, not a true tracker.
  - `detection.activity` enum: `stabbing | fistfight | purse_snatch | none`.
  - `relay.appearance` and `relay.direction` are their own fields.
  - On a `match` verdict, the agent also sends a new `relay` to the next camera.
  - `predict_next(camera_id, direction)` provided by the graph for `dispatch.predicted_next`.
- Mina added: `camera_status` heartbeat, `dispatch.incident_type` + `subject_appearance`, optional `run_id`/`source` on every event.
- Pending: Michael to review `dispatch` and `operator_action`.
