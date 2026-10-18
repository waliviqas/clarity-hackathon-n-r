"""LoRA fine-tune of the spotter (Qwen3-VL-2B) on the flashcards from make_train_data.py.

Each example is the exact request the spotter sends at test time (frames + PROMPT) followed by the
correct JSON answer. Loss is computed only on the answer tokens. The vision encoder stays frozen;
the LoRA adapter goes on the language model, which vLLM can serve with --enable-lora.
Runs on Brev in its own environment (~/ft), separate from vLLM.
"""
import argparse
import json
import random
import time
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

try:
    from .spotter_prompt import PROMPT
except ImportError:
    from spotter_prompt import PROMPT

BASE_MODEL = "Qwen/Qwen3-VL-2B-Instruct"
LORA_TARGETS = r".*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)"


def value_spans(answer: str, fields: list[str]) -> list[tuple[int, int]]:
    """Character ranges of the given fields' values inside the answer JSON."""
    spans = []
    for field in fields:
        value = json.dumps(json.loads(answer)[field])
        start = answer.index(f'"{field}": {value}') + len(f'"{field}": ')
        spans.append((start, start + len(value)))
    return spans


def build_example(processor, example: dict, learn_fields: list[str] | None = None) -> dict:
    """learn_fields: if given, only those answer fields are trained; everything else is left as the
    base model produces it (used to teach crime detection without memorizing who wore what)."""
    images = [Image.open(p).convert("RGB") for p in example["images"]]
    user = {"role": "user", "content": [*({"type": "image", "image": im} for im in images),
                                        {"type": "text", "text": PROMPT}]}
    assistant = {"role": "assistant", "content": [{"type": "text", "text": example["answer"]}]}
    prompt = processor.apply_chat_template([user], tokenize=True, add_generation_prompt=True,
                                           return_dict=True, return_tensors="pt")
    full = processor.apply_chat_template([user, assistant], tokenize=True, return_dict=True, return_tensors="pt")
    prompt_len = prompt["input_ids"].shape[1]
    if not torch.equal(full["input_ids"][0, :prompt_len], prompt["input_ids"][0]):
        raise ValueError("Prompt tokens are not a prefix of the full example; chat template mismatch")
    labels = full["input_ids"].clone()
    labels[:, :prompt_len] = -100  # only learn the answer, not the question
    if learn_fields:
        encoded = processor.tokenizer(example["answer"], return_offsets_mapping=True, add_special_tokens=False)
        answer_ids = torch.tensor(encoded["input_ids"])
        if not torch.equal(full["input_ids"][0, prompt_len:prompt_len + len(answer_ids)], answer_ids):
            raise ValueError("Answer tokens don't line up with the full example")
        spans = value_spans(example["answer"], learn_fields)
        keep = [any(s < end and e > start for start, end in spans) for s, e in encoded["offset_mapping"]]
        for i, k in enumerate(keep):
            if not k:
                labels[0, prompt_len + i] = -100
        labels[0, prompt_len + len(answer_ids):] = -100  # end-of-turn tokens
    full["labels"] = labels
    return full


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="train_data/train.jsonl")
    parser.add_argument("--out", default="lora/spotter-ft")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--accum", type=int, default=4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--learn-fields", default="", help="comma-separated answer fields to train, e.g. on_screen,crime")
    args = parser.parse_args()
    learn_fields = [f for f in args.learn_fields.split(",") if f] or None

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    processor = AutoProcessor.from_pretrained(BASE_MODEL)
    model = Qwen3VLForConditionalGeneration.from_pretrained(BASE_MODEL, dtype=torch.bfloat16, device_map="cuda")
    model = get_peft_model(model, LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05,
                                             target_modules=LORA_TARGETS, task_type="CAUSAL_LM"))
    model.print_trainable_parameters()

    examples = [json.loads(line) for line in open(args.data)]
    batches = [build_example(processor, e, learn_fields) for e in examples]
    if learn_fields:
        trained = sum(int((b["labels"] != -100).sum()) for b in batches) // len(batches)
        print(f"Training only on {learn_fields}: ~{trained} answer tokens per example")
    print(f"{len(batches)} examples, prompt+answer ~{sum(b['input_ids'].shape[1] for b in batches) // len(batches)} tokens each")

    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.0)
    total_steps = args.epochs * len(batches) // args.accum
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda step: max(0.0, 1 - step / max(1, total_steps)))

    model.train()
    log, step, start = [], 0, time.time()
    for epoch in range(args.epochs):
        order = list(range(len(batches)))
        random.shuffle(order)
        running = 0.0
        for i, idx in enumerate(order, 1):
            batch = {k: v.to("cuda") for k, v in batches[idx].items()}
            loss = model(**batch).loss / args.accum
            loss.backward()
            running += loss.item()
            if i % args.accum == 0 or i == len(order):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                step += 1
                if step % 5 == 0:
                    print(f"epoch {epoch + 1} step {step}/{total_steps} loss {running / (i / args.accum):.4f}")
        log.append({"epoch": epoch + 1, "mean_loss": round(running / (len(order) / args.accum), 4)})
        print(f"epoch {epoch + 1} done, mean loss {log[-1]['mean_loss']}")

    out = Path(args.out)
    model.save_pretrained(out)
    (out / "train_log.json").write_text(json.dumps({
        "base_model": BASE_MODEL, "examples": len(batches), "epochs": args.epochs, "lr": args.lr,
        "lora_rank": args.rank, "minutes": round((time.time() - start) / 60, 1), "epochs_log": log}, indent=2))
    print(f"Saved adapter to {out}")


if __name__ == "__main__":
    main()
