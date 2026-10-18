"""Merge the trained LoRA add-on into a full copy of the spotter model.

vLLM 0.11 crashes when serving a LoRA add-on on Qwen3-VL with image inputs, so we serve the merged
model as a normal model instead. Runs on Brev in the training environment (~/ft).
"""
import argparse

import torch
from peft import PeftModel
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

BASE_MODEL = "Qwen/Qwen3-VL-2B-Instruct"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default="lora/spotter-ft")
    parser.add_argument("--out", default="models/spotter-ft-merged")
    args = parser.parse_args()

    base = Qwen3VLForConditionalGeneration.from_pretrained(BASE_MODEL, dtype=torch.bfloat16)
    merged = PeftModel.from_pretrained(base, args.adapter).merge_and_unload()
    merged.save_pretrained(args.out)
    AutoProcessor.from_pretrained(BASE_MODEL).save_pretrained(args.out)  # tokenizer, image settings, chat template
    print(f"Saved merged model to {args.out}")


if __name__ == "__main__":
    main()
