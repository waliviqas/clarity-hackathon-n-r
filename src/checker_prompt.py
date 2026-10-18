"""The checker's one job: describe the suspect. Same field names and enums as the spotter's answer, so the
same grader scores it and the two answers can be combined."""
try:
    from .spotter_prompt import SCHEMA
except ImportError:
    from spotter_prompt import SCHEMA

DESCRIBE_FIELDS = ["build", "height", "shirt", "pants", "shoes", "glasses", "headwear", "hair", "bag", "weapon", "vehicle"]

DESCRIBE_SCHEMA = {
    "type": "object",
    "properties": {f: SCHEMA["properties"][f] for f in DESCRIBE_FIELDS},
    "required": DESCRIBE_FIELDS,
}

# v1, scored in NeMo Gym on Oct 18 ~3 AM. Its example values were copied into answers (pants "blue jeans" every time).
DESCRIBE_PROMPT_V1 = """These are frames from one security camera, in time order. A crime just happened here, or someone is running away from one.

Describe only the suspect: the person who attacks, steals, or runs away. Never describe the victim (the person who gets hurt, falls, or loses something).

Give the colour and type of each item, for example shirt "black hoodie", pants "blue jeans", shoes "white sneakers", hair "short dark". Use "unknown" only if that part of the suspect cannot be seen in any frame. For headwear, bag, weapon and vehicle, use "none" if the suspect clearly has none."""

# v2: no example values to copy (only a "<colour> <kind of item>" form), and estimates instead of "unknown"
# for build, height and glasses. Developed on the train split only.
DESCRIBE_PROMPT = """These are frames from one security camera, in time order. A crime just happened here, or someone is running away from one.

Describe only the suspect: the person who attacks, steals, or runs away. Never describe the victim (the person who gets hurt, falls, or loses something).

For shirt, pants and shoes, always give both the colour and the kind of item, in the form "<colour> <kind of item>", never the colour alone. For hair, give its length or style and its colour. Look at each item separately in the frames; do not guess from the other items.

Build and height: give your best estimate from the suspect's body shape and from the people, doors and cars around them. Use "unknown" only if the suspect's body cannot be seen at all.
Glasses: "no" if the suspect's face is visible in any frame without glasses.

Use "unknown" for anything else only if that part of the suspect cannot be seen in any frame. For headwear, bag, weapon and vehicle, use "none" if the suspect clearly has none."""

CRIME_SCHEMA = {
    "type": "object",
    "properties": {"crime": {"type": "string", "enum": ["stabbing", "assault", "stealing", "none"]}},
    "required": ["crime"],
}

CRIME_PROMPT = """These are frames from one security camera, in time order. Another camera model thinks a crime happens here.

Which crime is it?
- "stabbing": someone makes stabbing or jabbing motions into another person's body, with or without a visible knife
- "assault": someone hits, punches, kicks or shoves another person, with no stabbing
- "stealing": someone takes another person's property, including pickpocketing, snatching a phone or bag, or stealing a vehicle
- "none": no crime happens, or you cannot tell"""

# Relay: the next camera along the suspect's path asks the checker whether the relayed suspect is here.
MATCH_SCHEMA = {
    "type": "object",
    "properties": {"present": {"type": "string", "enum": ["yes", "no"]}, **DESCRIBE_SCHEMA["properties"]},
    "required": ["present", *DESCRIBE_FIELDS],
}

MATCH_PROMPT = """These are frames from one security camera, in time order. A moment ago, the previous camera on this street saw a suspect running away from a crime. It described the suspect as:
{description}

Is this suspect visible in these frames? Answer "present": "yes" only if you see a person whose clothing matches the description. People who look different, or no people at all, mean "no".

Then describe the person you think is the suspect, using the same rules as before: for shirt, pants and shoes give "<colour> <kind of item>"; for hair give its length or style and its colour; give your best estimate of build and height; glasses "no" if the face is visible without glasses; "unknown" only if that part cannot be seen; for headwear, bag, weapon and vehicle use "none" if the person clearly has none. If "present" is "no", use "unknown" for build, height and glasses and "none" for everything else."""


def describe_text(answer: dict) -> str:
    """A checker description as one line for the relay, keeping only what was seen."""
    parts = [f"{f}: {answer[f]}" for f in DESCRIBE_FIELDS
             if str(answer.get(f, "")).strip().lower() not in ("", "none", "unknown")]
    return "; ".join(parts) or "no details"
