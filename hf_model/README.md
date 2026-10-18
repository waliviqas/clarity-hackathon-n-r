---
license: apache-2.0
base_model: Qwen/Qwen3-VL-2B-Instruct
pipeline_tag: image-text-to-text
datasets:
- waliviqas/clarity-crime-clips
---

# Clarity spotter (Qwen3-VL-2B, fine-tuned)

Spots a crime on a security camera and names the type (stabbing, assault, stealing). Part of
[Clarity](https://github.com/waliviqas/clarity-hackathon-n-r), NVIDIA x Red Hat Small Models Hack 2026.

## Improvement at every training run

Scored in NeMo Gym on the same 18 held-out test cameras × 3 runs, 8 frames per camera. **Full system** = this spotter
decides crime and type, and NVIDIA Nemotron Nano 12B v2 VL describes the suspect on the cameras the spotter flags.

| Version | What changed | Spotter score | Full system score | Crime spotted | Crime type | False alarms |
|---|---|---|---|---|---|---|
| Base Qwen3-VL-2B | — | 0.374 | 0.723 | 67% | 17% | 0% |
| v1 | trained on our clips, all fields | 0.616 ⚠️ | 0.812 | 89% | 50% | **50%** |
| v2 | + 11 public clips, all fields | 0.654 ⚠️ | 0.815 | 87% | 17% | 0% |
| **v3 (this model)** | **trained on crime + type only** | **0.456** | **0.821** | **89%** | **33%** | **0%** |
| v4 | + 113 public clips (×9) | 0.377 | 0.660 | 70% | 33% | 0% |
| v5 | + 113 public clips (×1) | 0.401 | 0.731 | 72% | 33% | 0% |
| v3 retrained on 8 frames | same data, 8 frames | 0.358 | 0.744 | 72% | 33% | 0% |

⚠️ v1 and v2 score higher on their own because they **memorized the outfits** of the few actors in our training clips,
and the test clips use the same actors in the same clothes. On a new clip they copied a training suspect's clothes
onto the wrong person, and v1 raised false alarms on half of the normal scenes. That's why v3 trains only on the crime
fields, and why the suspect description comes from Nemotron instead.

## Base vs this model

| | Base | This model |
|---|---|---|
| Crime spotted | 67% | **89%** |
| Crime type | 17% | **33%** |
| False alarms | 0% | 0% |
| Answers not cut off | 51 / 54 | **54 / 54** |
| **Spotter score** | 0.374 | **0.456** |
| **Full system score** | 0.723 | **0.821** |

LoRA (rank 16) merged into the base model, 2.13B parameters. Use the prompt in
[`src/spotter_prompt.py`](https://github.com/waliviqas/clarity-hackathon-n-r/blob/wali-branch/src/spotter_prompt.py).
