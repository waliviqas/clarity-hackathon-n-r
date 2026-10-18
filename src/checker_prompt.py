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
