#!/usr/bin/env bash
# Serve the checker (Nemotron Nano 12B v2 VL) with vLLM on the team's Brev box. Run inside tmux:
#   tmux new -s checker     # or: tmux attach -t checker
#   bash infra/serve_checker.sh
# src/checker.py calls it (CHECKER_BASE_URL=http://localhost:8002/v1, CHECKER_MODEL=checker).
#
# --host 127.0.0.1: only reachable from the box itself and through the port-forward/SSH tunnel.
# vLLM 0.11.0 from ~/vllm12: newer vLLM doesn't work with this GPU's driver.
# --limit-mm-per-prompt: 8 images per request; video 0 because vLLM's video warm-up crashes on this model.
# The first request after startup takes ~15-60 s; then ~5 s per camera (8 frames).
set -euo pipefail
source ~/vllm12/bin/activate
exec vllm serve nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16 \
  --served-model-name checker \
  --host 127.0.0.1 --port 8002 \
  --gpu-memory-utilization 0.40 \
  --max-model-len 16384 \
  --limit-mm-per-prompt '{"image": 8, "video": 0}' \
  --trust-remote-code
