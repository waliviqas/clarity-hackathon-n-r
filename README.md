# Clarity
[![Clarity demo video](https://markdown-videos-api.jorgenkh.no/youtube/VknNMVP4zog?width=1280&height=720)](https://www.youtube.com/watch?v=VknNMVP4zog)

**6 minutes and 17 seconds.** That's the median amount of time it takes to call the police about a serious crime. With Clarity, it happens instantly.

## How it works

## Under the hood

Three small AI models, all running on one GPU with vLLM:

1. **Spotter** (Qwen 2B, fine-tuned by us): watches every camera and spots the crime.
2. **Checker** (NVIDIA Nemotron 12B): describes what the suspect is wearing, so the next cameras can find them.
3. **Dispatcher** (NVIDIA Nemotron 9B): tells officers where to go. A person approves every alert.

Only text moves between cameras, never video.

## Results

Tested in NeMo Gym on our own videos the model never trained on:

- The spotter makes the right call on **89%** of cameras (crime, someone running, or nothing), up from **67%** before fine-tuning.
- The full system gets **82%** of its checks right.

## Links

- Fine-tuned model: https://huggingface.co/waliviqas/clarity-spotter-qwen3vl-2b
- Our videos (open data): https://huggingface.co/datasets/waliviqas/clarity-crime-clips
- NeMo Gym setup and scores: [`nemo_gym/`](nemo_gym/), [`results/`](results/)
- vLLM write-up: [`VLLM_BOUNTY.md`](VLLM_BOUNTY.md)
- Everything else (how to run, data sources, limitations): [`DETAILS.md`](DETAILS.md)

## Team

Wali Viqas, Michael Venecia, Mina Abdel-Masih

Built at the NVIDIA x Red Hat Small Models Hack, Raleigh, Oct 17–18 2026. Track: **Fine-Tuned**.
