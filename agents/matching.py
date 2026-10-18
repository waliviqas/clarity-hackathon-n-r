"""Plain-code checks a camera agent runs when a relayed suspect may have reached its camera (no model).

1. Looks: does this camera's spotter answer describe the same person? Compared field by field (shirt,
   pants, hair, ...). A field either side couldn't see is skipped, so "unknown" never counts against.
2. Behaviour: someone running (or committing a crime) is more likely the fleeing suspect; "nothing
   suspicious" is less likely.
3. Timing: the gap between the two clips has to fit the link's travel_time_s (generous margins).

Looks and behaviour give a sighting probability: how likely the person seen here is the relayed suspect.
Weak sightings along one route add up (noisy-OR): two at 50% give 75%; five at 20% give 67%, more than
one at 60%. A match needs at least one feature that agrees: behaviour alone (someone running, no
description) is "uncertain" at most, and its look doesn't add up with earlier weak sightings.
"""
from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

# How much each feature says about who someone is (a shirt is easy to see; a vehicle is often the scene's).
WEIGHTS = {"shirt": 3.0, "pants": 2.0, "headwear": 2.0, "bag": 1.5, "hair": 1.0, "shoes": 1.0,
           "build": 1.0, "height": 1.0, "glasses": 1.0, "weapon": 1.0, "vehicle": 0.5}
LEVELS = {"build": ("slim", "average", "heavy"), "height": ("short", "average", "tall")}
ITEM_FIELDS = {"headwear", "bag", "weapon", "vehicle"}  # "none" there means "clearly has none"
# Features that tell people apart. Glasses, height and build agree for most passers-by, so they can add to the
# score but never be the one agreeing feature a "match" needs.
DISTINCTIVE = ("shirt", "pants", "shoes", "headwear", "hair", "bag")
UNKNOWN = {"", "unknown", "unclear", "unsure", "not visible", "n/a", "na"}

COLOURS = {"black", "white", "grey", "red", "blue", "navy", "green", "yellow", "orange", "purple", "pink",
           "brown", "beige", "tan", "khaki", "cream", "maroon", "silver", "gold", "dark", "light"}
SAME_COLOUR = [{"navy", "blue"}, {"maroon", "red"}, {"beige", "tan", "khaki", "cream"}, {"grey", "silver"}]
DARK = {"black", "navy", "grey", "brown", "maroon"}  # what "dark" can mean
LIGHT = {"white", "beige", "cream", "tan", "khaki", "grey", "silver", "yellow"}  # ...and "light"
SYNONYMS = {"gray": "grey", "hooded": "hoodie", "hoody": "hoodie", "sweatshirt": "hoodie", "denim": "jeans",
            "trousers": "pants", "sweatpants": "pants", "joggers": "pants", "sneaker": "sneakers",
            "trainers": "sneakers", "cap": "hat", "beanie": "hat", "tee": "tshirt"}
# Words that say nothing about who it is ("black shirt" vs "black hoodie" compares the colour only).
FILLER = {"a", "an", "the", "and", "with", "of", "in", "on", "or", "his", "her", "colored", "coloured",
          "color", "colour", "shirt", "top", "pants", "shoes", "hair", "clothes", "clothing", "wearing",
          "possibly", "maybe", "some"}

PRIOR = 0.3         # someone on the expected camera at a plausible time, before looking at them
BEHAVIOUR = 0.85    # log-odds: running or committing a crime (0.3 -> 0.5); "nothing suspicious" (0.3 -> 0.15)
PER_WEIGHT = 0.5    # log-odds per unit of feature weight that agrees (or differs)
MATCH_AT = 0.6      # a sighting (or the weak sightings since the last match, combined) this likely is a match
WEAK_AT = 0.2       # below this it isn't them; in between it's "uncertain"
MIN_CONFIDENCE, MAX_CONFIDENCE = 0.05, 0.95  # a 2B model and simple rules never justify certainty

FASTEST = 0.5           # nobody covers a link in under half its measured time...
SLOWEST = 3.0           # ...or takes more than three times as long,
SLACK_S = 30.0          # plus half a minute (stopping, hiding, a crowd)
UNKNOWN_LINK_S = 120.0  # a link without travel_time_s: anything up to two minutes


def features(answer: dict) -> dict[str, str]:
    """The suspect's described features from one spotter answer, lower-cased. Fields the spotter couldn't
    see are left out. "none" is kept for headwear/bag/weapon/vehicle ("clearly has none"); for shirt, pants,
    shoes and hair the spotter writes "none" when it saw no suspect, so there it means unknown."""
    out = {}
    for field in WEIGHTS:
        value = " ".join(str(answer.get(field) or "").lower().split())
        if field in ITEM_FIELDS and (value in ("no", "nothing") or value.startswith("no ")):
            value = "none"
        if value in UNKNOWN or (value == "none" and field not in ITEM_FIELDS):
            continue
        out[field] = value
    return out


def _words(text: str) -> tuple[set[str], set[str]]:
    """(colour words, other words) of one free-text value, synonyms folded and filler dropped."""
    tokens = re.findall(r"[a-z0-9]+", text.lower().replace("t-shirt", "tshirt"))
    words = {SYNONYMS.get(t, t) for t in tokens} - FILLER
    return words & COLOURS, words - COLOURS


def _close_colours(x: str, y: str) -> bool:
    return (x == y or any(x in g and y in g for g in SAME_COLOUR)
            or (x == "dark" and y in DARK) or (y == "dark" and x in DARK)
            or (x == "light" and y in LIGHT) or (y == "light" and x in LIGHT))


def text_agreement(a: str, b: str) -> float | None:
    """1 = same, 0.5 = same colour but another item (black hoodie vs black jacket), 0 = different,
    None = nothing comparable ("black" vs "hoodie")."""
    colours_a, items_a = _words(a)
    colours_b, items_b = _words(b)
    colours = any(_close_colours(x, y) for x in colours_a for y in colours_b) if colours_a and colours_b else None
    items = bool(items_a & items_b) if items_a and items_b else None
    if colours is False:
        return 0.0
    if items is False:
        return 0.5 if colours else 0.0
    return 1.0 if (colours or items) else None


def field_agreement(field: str, a: str, b: str) -> float | None:
    """How well two values of one feature agree (1 / 0.5 / 0), or None if they can't be compared."""
    if field in LEVELS:
        order = LEVELS[field]
        if a not in order or b not in order:
            return None
        gap = abs(order.index(a) - order.index(b))
        return 1.0 if gap == 0 else 0.5 if gap == 1 else 0.0
    if field == "glasses":
        return float(a == b) if {a, b} <= {"yes", "no"} else None
    if a == "none" and b == "none":
        return None  # both clearly without: says little (most people carry no bag or weapon)
    if "none" in (a, b):
        return 0.0
    return text_agreement(a, b)


def compare(expected: dict[str, str], seen: dict[str, str]) -> dict[str, float]:
    """Agreement per feature both sides describe (output of features())."""
    out = {}
    for field in WEIGHTS:
        if field in expected and field in seen:
            agreement = field_agreement(field, expected[field], seen[field])
            if agreement is not None:
                out[field] = agreement
    return out


def sighting_probability(agreements: dict[str, float], on_screen: str | None) -> float:
    """How likely this is the relayed suspect: a prior, nudged by behaviour and by each compared feature."""
    x = math.log(PRIOR / (1 - PRIOR))
    if on_screen in ("crime", "fleeing"):
        x += BEHAVIOUR
    elif on_screen == "none":
        x -= BEHAVIOUR
    x += PER_WEIGHT * sum(WEIGHTS[f] * (2 * a - 1) for f, a in agreements.items())
    return 1 / (1 + math.exp(-x))


def combine(probabilities) -> float:
    """Noisy-OR: the chance that at least one of these weak sightings really was the suspect."""
    miss = 1.0
    for p in probabilities:
        miss *= 1 - p
    return 1 - miss


def arrival_bounds(travel_s: float | None) -> tuple[float, float]:
    """Shortest and longest plausible time between leaving one camera's view and reaching the next."""
    if travel_s is None:
        return 0.0, UNKNOWN_LINK_S
    return travel_s * FASTEST, travel_s * SLOWEST + SLACK_S


def check_timing(left: tuple[float, float], seen: tuple[float, float], travel_s: float | None,
                 from_camera: str) -> tuple[bool, str]:
    """Could the suspect seen during clip `left` (run-clock start, end) be the person in clip `seen`?
    Clip-level answers only say "somewhere in this clip", so the gap is a range."""
    low, high = arrival_bounds(travel_s)
    gap_min, gap_max = seen[0] - left[1], seen[1] - left[0]
    if gap_max < low:
        return False, f"Too soon: at most {gap_max:.1f} s after {from_camera}; the walk takes at least {low:.1f} s."
    if gap_min > high:
        return False, f"Too late: at least {gap_min:.0f} s after {from_camera}; expected within {high:.0f} s."
    walk = f"walk ~{travel_s:g} s" if travel_s is not None else "walk time unknown"
    return True, f"Timing fits ({max(gap_min, 0):.1f}-{gap_max:.1f} s after {from_camera}, {walk})."


@dataclass
class Judgement:
    decision: str          # "match" | "no_match" | "uncertain"
    sighting: float        # this camera's own look: how likely it's the relayed suspect
    probability: float     # the same, combined with the weak sightings since the last match
    confidence: float      # for agent_verdict.confidence: how sure the agent is of `decision`
    reason: str            # for agent_verdict.reason
    keep_following: bool   # relay onward from this camera


def _clip(p: float) -> float:
    return round(min(MAX_CONFIDENCE, max(MIN_CONFIDENCE, p)), 2)


def _looks_words(agreements: dict[str, float]) -> str:
    """'Shirt, pants match; hair is close; vehicle differs'."""
    if not agreements:
        return "Nothing in the description to compare"
    groups = [(("match", "matches"), 1.0), (("are close", "is close"), 0.5), (("differ", "differs"), 0.0)]
    parts = []
    for (plural, single), level in groups:
        fields = [f for f, a in agreements.items() if a == level]
        if fields:
            parts.append(f"{', '.join(fields)} {plural if len(fields) > 1 else single}")
    text = "; ".join(parts)
    return text[:1].upper() + text[1:]


BEHAVIOUR_WORDS = {"crime": "committing a crime", "fleeing": "running", "none": "nothing suspicious"}


def judge(expected: dict[str, str], answer: dict, left: tuple[float, float], seen: tuple[float, float],
          travel_s: float | None, from_camera: str, earlier_weak: Sequence[tuple[str, float]] = ()) -> Judgement:
    """A camera agent's verdict on one relay, from its own spotter answer.

    expected: the relayed description (features()); left / seen: run-clock windows of the sender's clip
    and this camera's clip; earlier_weak: (camera_id, probability) of uncertain sightings on this route
    since the last match. Someone running who is uncertain can still be followed (Network(follow_uncertain=True)),
    so weak sightings can add up. "match" needs at least one feature that agrees (agreement 1).
    """
    fits, timing_words = check_timing(left, seen, travel_s, from_camera)
    if not fits:
        return Judgement("no_match", 0.0, 0.0, MAX_CONFIDENCE, timing_words, False)
    agreements = compare(expected, features(answer))
    on_screen = answer.get("on_screen")
    p = sighting_probability(agreements, on_screen)
    # Without one agreeing feature, two people running with no description would add up to 75%: a "match"
    # on behaviour alone. Such a look stays on its own (uncertain at most).
    agrees = any(agreements.get(f, 0.5) > 0.5 for f in DISTINCTIVE)
    combined = combine([q for _, q in earlier_weak] + [p]) if agrees else p
    if agrees and (p >= MATCH_AT or (p >= WEAK_AT and combined >= MATCH_AT)):
        decision = "match"
    elif p >= WEAK_AT:
        decision = "uncertain"
    else:
        decision = "no_match"
    behaviour = BEHAVIOUR_WORDS.get(on_screen, "behaviour not reported")
    words = [f"{_looks_words(agreements)}; {behaviour} here.", timing_words]
    cams = ", ".join(c for c, _ in earlier_weak)
    if decision == "no_match":
        words.append(f"{p:.0%} likely the same person.")
    elif earlier_weak and not agrees:
        words.append(f"No feature agrees, so the weak sightings at {cams} don't add up; {p:.0%} likely.")
    elif earlier_weak and p < MATCH_AT:
        words.append(f"This look {p:.0%}; with the weak sightings at {cams}, {combined:.0%} likely.")
    elif not agrees:
        words.append(f"No feature agrees, so not a match; {p:.0%} likely the same person.")
    else:
        words.append(f"{combined:.0%} likely the same person.")
    reason = " ".join(words)
    if len(reason) > 300:
        reason = reason[:297] + "..."
    confidence = _clip(1 - p if decision == "no_match" else combined)
    keep = decision == "match" or (decision == "uncertain" and on_screen in ("crime", "fleeing"))
    return Judgement(decision, round(p, 3), round(combined, 3), confidence, reason, keep)


def merge(known: dict[str, str], seen: dict[str, str]) -> dict[str, str]:
    """After a match, the next camera gets a fuller description: fill fields that were unknown, never
    overwrite one that was seen (so the description can't drift to someone else)."""
    return {**seen, **known}
