#!/usr/bin/env bash
# Serve the dispatcher (coordinator) model with vLLM on the team's Brev box. Run inside tmux:
#   tmux new -s dispatcher     # or: tmux attach -t dispatcher
#   bash infra/serve_dispatcher.sh
# Reach it from a laptop with: brev port-forward clarity --port 8003:8003
#
# --host 127.0.0.1: only reachable from the box itself (and through the port-forward/SSH tunnel), not from the
#   internet. vLLM's default would listen on every interface.
# vLLM 0.11.0 from ~/vllm12: newer vLLM doesn't work with this GPU's driver.
# Flags and measurements: dispatcher/README.md and VLLM_BOUNTY.md.
set -euo pipefail
source ~/vllm12/bin/activate
exec vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2 \
  --served-model-name dispatcher \
  --host 127.0.0.1 --port 8003 \
  --gpu-memory-utilization 0.30 \
  --max-model-len 8192 \
  --max-num-seqs 16 \
  --mamba_ssm_cache_dtype float32 \
  --enable-prefix-caching \
  --trust-remote-code
