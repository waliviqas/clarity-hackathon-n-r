# Session handoff (Michael's Claude Code session, Oct 17–18, 2026)

Read this first to resume. Hackathon: NVIDIA x Red Hat Small Models Hack (Raleigh), Fine-Tuned track + Best Use of Red Hat vLLM bounty. Code freeze was Sun Oct 18, 11:00.

## Team
- **Michael** (me): coordinator (`dispatcher/`), GPU/Brev serving, testing, vLLM bounty.
- **Wali**: spotter fine-tune (Qwen3-VL-2B + LoRA v3), checker, NeMo Gym, `scripts/demo_control.py`.
- **Mina**: camera agents, event bus, dashboard, contracts, data.

## Working rules
- Hackathon mode: no teaching mode; just build.
- Before any push, scan for sensitive content (keys, tokens, IPs, emails, `.env`, raw videos).
- Branch flow: Michael → Integration → main. Normally don't push to main; the user once explicitly approved pushing only `vllm_bounty/` to main.
- On the Brev box, don't touch other people's tmux sessions (`qwen`, `spotter-ft`, `gym`, `checker`, `demo3-*`) or `~/clarity-bench`.

## System
- 3 models on vLLM 0.11.0, one A100 80 GB (Brev box "clarity"): spotter-ft :8005 (0.20), checker Nemotron Nano 12B v2 VL :8002 (0.40), coordinator Nemotron Nano 9B v2 :8003 (0.30). 24.20B params total.
- Coordinator: rules first (stabbing alerts immediately), the model writes the recommendation as strict JSON, a verifier checks it, one retry, then "Operator review needed". A human confirms every alert. 79 tests in `tests/test_dispatcher.py`.
- Key numbers:
  - Fine-tune: right calls 67→89%, full-system score 0.723→0.821, crime type 17→33%, false alarms 0%.
  - vLLM: coordinator throughput ~7× at 16 concurrent incidents; spotter 88→993 cameras/min; call latency 13.3→1.6 s; first alert 21.9→1.59 s (live run `runs/run_live2_1027`).

## Done
- `vllm_bounty/README.md`: full vLLM write-up plus an evidence table. **On main** (46f4d21). Integration also has the root `VLLM_BOUNTY.md` pointer and README/DETAILS link updates (769f84f), not yet on main.
- `presentation/index.html`: short scroll website (Wali's original 4 acts + how it works, fine-tune, team). On Integration/main.
- Michael branch == Integration (f590caf).

## Open / pending
- `TECH_STACK.md` (whole-team tech list, names only) written locally at the repo root; not committed. Mina's `TECH.md` covers only her part.
- Demo video: my part is the coordinator + vLLM (~45–60 s script: rules → model → verifier → human Confirm; one GPU, ~7×, 1.59 s).
- Box: my old tmux sessions `bus-live` / `disp-live` still hold port 8080 (stale run); Wali's demo bus runs on 8081 and control on 8090 (`~/clarity-repo`, `.env.demo3`).
- Local dashboard viewer used a tunnel to 8081/8090 (brev SSH uses ControlMaster; use `-o ControlMaster=no -o ControlPath=none` for a lasting tunnel).
