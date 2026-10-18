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

DESCRIBE_PROMPT = """These are frames from one security camera, in time order. A crime just happened here, or someone is running away from one.

Describe only the suspect: the person who attacks, steals, or runs away. Never describe the victim (the person who gets hurt, falls, or loses something).

Give the colour and type of each item, for example shirt "black hoodie", pants "blue jeans", shoes "white sneakers", hair "short dark". Use "unknown" only if that part of the suspect cannot be seen in any frame. For headwear, bag, weapon and vehicle, use "none" if the suspect clearly has none."""

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
