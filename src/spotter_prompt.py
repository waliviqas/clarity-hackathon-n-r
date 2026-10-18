"""The spotter's prompt and answer format, shared by spotter.py (serving) and finetune.py (training)."""

# vLLM forces the reply to match this schema, so the output always has these fields.
# what_happened comes first so the model describes the scene before it classifies it.
SCHEMA = {
    "type": "object",
    "properties": {
        "what_happened": {"type": "string"},
        "on_screen": {"type": "string", "enum": ["crime", "fleeing", "none"]},
        "crime": {"type": "string", "enum": ["stabbing", "assault", "stealing", "none"]},
        "build": {"type": "string", "enum": ["slim", "average", "heavy", "unknown"]},
        "height": {"type": "string", "enum": ["short", "average", "tall", "unknown"]},
        "shirt": {"type": "string"},
        "pants": {"type": "string"},
        "shoes": {"type": "string"},
        "glasses": {"type": "string", "enum": ["yes", "no", "unknown"]},
        "headwear": {"type": "string"},
        "hair": {"type": "string"},
        "bag": {"type": "string"},
        "weapon": {"type": "string"},
        "vehicle": {"type": "string"},
    },
    "required": ["what_happened", "on_screen", "crime", "build", "height", "shirt", "pants",
                 "shoes", "glasses", "headwear", "hair", "bag", "weapon", "vehicle"],
}

PROMPT = """These are frames from one security camera, in time order.

First, describe what happens in one or two short sentences ("what_happened").

Then decide what is on screen:
- "crime": a crime happens in these frames: stabbing, assault (hitting, punching, shoving), or stealing (taking someone's property, including pickpocketing, snatching, or stealing a vehicle)
- "fleeing": no crime happens here, but someone is running away as if escaping
- "none": nothing suspicious

"crime" is the type of crime you see. If someone is fleeing, use the crime they appear to be escaping from if you can tell, otherwise "none".

The suspect is the person committing the crime or running away, not the victim (the person who gets hurt, falls, or loses something). Describe only the suspect. Use "unknown" for anything you cannot see clearly. For headwear, bag, weapon and vehicle, use "none" if the suspect clearly has none. If there is no suspect, use "unknown" for build, height and glasses, and "none" for the other description fields."""
