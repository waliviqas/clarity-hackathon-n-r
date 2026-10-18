---
license: cc-by-4.0
task_categories:
- video-classification
- visual-question-answering
tags:
- surveillance
- crime-detection
- multi-camera
- synthetic
- staged
pretty_name: Clarity staged crime clips
size_categories:
- n<1K
---

# Clarity staged crime clips

Staged multi-camera "security camera" footage of a crime and the suspect's escape, made for **Clarity**,
a multi-agent system that spots a crime on one camera and follows the suspect across the next ones.
Built at the NVIDIA x Red Hat Small Models Hack (Raleigh, NC, Oct 17–18 2026).

**Every incident is staged.** No real crime took place and no one was hurt. Everyone on screen is a
member of our team or a volunteer who agreed to be filmed and to have the footage published.

## What's in it

- `clips/clipN/clipN.mp4`: one incident, all camera angles joined in order (13 incidents)
- `clips/clipN/camK.mp4`: the same incident split into one file per camera angle (34 camera files)
- `labels.csv`: one row per camera file (the answer key)
- `camera_positions.csv`: where each camera stood and when it recorded

| Crime | Incidents |
|---|---|
| stabbing (fake, staged motion) | 5 |
| stealing (pickpocket, phone snatch, car) | 4 |
| assault (punch) | 2 |
| nothing happens (normal scenes) | 2 |

## How it was made

- **Filmed:** Oct 17 2026 in downtown Raleigh, NC (sidewalks, a café patio, a parking deck, a bus stop, indoor halls), on an iPhone 14 Plus held at about CCTV height.
- **Staging:** for each incident, one person commits the staged crime on camera 1 and runs off; we then re-filmed the escape from the next camera spots in order (camera 2, 3, …). Clips were joined in order and normalised to 30 fps H.264, then split back into one file per camera at the angle changes.
- **Camera positions:** latitude/longitude read from each original iPhone video (iPhone stores 4 decimal places, about ±11 m; garage/indoor shots are less accurate, see `gps_accuracy_m`). `recorded_at` is the phone clock; gaps between cameras include walking to the next spot, so they are not run times.
- **Labels:** each camera was labelled with what is on screen (`crime` / `fleeing` / `none`), the crime type, a one-sentence description, and the attacker's appearance by **clothing and build only** (no skin colour, race or face). Labels were drafted with an AI assistant from sampled frames and then checked and corrected by the team.
- **Split:** `split=test` cameras (incidents 1, 3, 4, 7, 8, 12, 13) were only ever used to evaluate; `split=train` cameras were used for fine-tuning. Never train on the test rows if you want comparable numbers.

## Label columns

`clip, cam, split, on_screen, crime, what_happened, build, height, shirt, pants, shoes, glasses, headwear, hair, bag, weapon, vehicle, check`

- `on_screen`: crime / fleeing / none · `crime`: stabbing / assault / stealing / none
- `build`: slim / average / heavy / unknown · `height`: short / average / tall / unknown · `glasses`: yes / no / unknown
- other appearance fields are free text; `unknown` = not visible, `none` = clearly absent

## Limitations

- Small: 13 incidents, and only a few people, who swap attacker/victim roles between clips. Models trained on it can learn *who* rather than *what*; we saw exactly that.
- One city block, one afternoon, one phone.
- Staged motion (especially the fake stabbings) is cleaner than real footage.

## License and citation

CC BY 4.0. Please credit "Clarity team, NVIDIA x Red Hat Small Models Hack 2026".
