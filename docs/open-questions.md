# Open questions

Check here before assuming. When one is decided, move it to "Decided" with the date and who decided.

## For the organizers (ask in `#small-models-hack-raleigh`)

| # | Question | Why it matters | Asked? | Answer |
|---|---|---|---|---|
| O1 | Exact demo-video criteria and upload format | The Notion page needs a browser to read | | |
| O2 | Confirm that non-language vision models (if any are added, e.g. a YOLO detector) don't count toward 33B | Only matters if we add one | | |

(The 33B cap is combined: the rule text says "the total params of all generative language models". No need to ask.)

## For the team

| # | Question | Owner | Status |
|---|---|---|---|
| T1 | Who owns the event bus that feeds the dashboard? (Mina proposed owning it; Wali's relay uses an inbox per agent, and the dashboard still needs one stream of all events.) | Team | Open |
| T2 | Where exactly does the checker sit: confirming the spotter's flag, matching the suspect at the next camera, or both? | Wali | Open |
| T3 | What does the lookup (RAG) retrieve, and from which open source? (It needs a documented, licensed source like everything else.) | Michael | Open |
| T4 | GPU memory plan for 3 vLLM servers + embed + rerank on one Brev GPU (BF16 vs FP8) | Michael | Open |
| T5 | If the spotter is fine-tuned: which clips are train vs. test (must not overlap), and are they published? | Wali + Mina | Open |
| T6 | Staging: how to film three simultaneous incidents (which cameras, who acts, timing) | Mina | Open |
| T7 | Stabbing: no openly licensed footage exists, and props at the venue are a safety problem. Keep it as a detectable label but demo fistfight + purse snatch? | Team | Open (recommended) |
| T8 | Map: MEVA site (if used) vs. staged cameras around the Red Hat Annex, or both | Mina | Open |
| T9 | Live iPhone feed vs. record-and-replay | Mina | Open; record-and-replay is the safe default |
| T10 | Map library: Leaflet + OpenStreetMap (no key, open data, recommended) vs. Google Maps (API key with billing) | Mina | Open |
| T11 | Michael's review of the `dispatch` and `operator_action` schemas | Michael | Open |

## Decided

| Date | Decision | By |
|---|---|---|
| Oct 17 | Project name: Clarity | Team |
| Oct 17 | Ownership split (see `CLAUDE.md`) | Team |
| Oct 17 | Contracts v0.1 with Wali's changes (words for suspect descriptions, direction field) | Mina + Wali |
| Oct 17 | All Python runs on Brev; dashboard on Mina's laptop | Team |
| Oct 17 | Models: Qwen3-VL-2B spotter, Nemotron Nano 12B v2 VL checker, Nemotron Nano 9B v2 dispatcher, Nemotron Embed + Rerank lookup (≈ 23.6B). Lightning dropped. | Team |
| Oct 17 | Camera graph in NetworkX (not Jac) | Wali |
| Oct 17 | Demo shows three crimes at once | Team |
