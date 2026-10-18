"""Score the two-model system with the same grader as NeMo Gym: the spotter decides what is on screen; the checker
is only asked about cameras the spotter flagged (crime or fleeing), as in the real pipeline. Elsewhere the
spotter's own answer stands.

--vote: the incident's crime type is a majority vote of every camera the spotter flagged (crime or fleeing) in
the same clip and the same run; a tie goes to what the crime camera(s) said. Uses only the spotter's answers.

python results/combine_gym.py SPOTTER.jsonl DESCRIBE.jsonl OUT.jsonl [--crime CRIME.jsonl] [--vote]
"""
import argparse, collections, json, sys
sys.path.insert(0, "resources_servers/clarity_spotter")
from app import EXACT_FIELDS, TEXT_FIELDS, is_scorable, text_match

CRIMES = ("stabbing", "assault", "stealing")

parser = argparse.ArgumentParser()
parser.add_argument("spotter")
parser.add_argument("describe")
parser.add_argument("out")
parser.add_argument("--crime", help="checker crime-type rollouts; used where the spotter says crime")
parser.add_argument("--vote", action="store_true", help="crime type = vote of all flagged cameras in the incident")
args = parser.parse_args()

tasks = [json.loads(l) for l in open("resources_servers/clarity_spotter/data/test.jsonl")]
def load(path):
    return {(r["_ng_task_index"], r["_ng_rollout_index"]): r for r in map(json.loads, open(path))} if path else {}
spot, describe, crime = load(args.spotter), load(args.describe), load(args.crime)

voted = {}
if args.vote:
    votes, crime_cam = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for (ti, run), s in spot.items():
        p = s["predicted"] or {}
        if p.get("on_screen") in ("crime", "fleeing") and p.get("crime") in CRIMES:
            votes[(tasks[ti]["clip"], run)][p["crime"]] += 1
            if p["on_screen"] == "crime":
                crime_cam[(tasks[ti]["clip"], run)][p["crime"]] += 1
    for incident, counts in votes.items():
        top = max(counts.values())
        tied = [c for c in CRIMES if counts[c] == top]
        voted[incident] = tied[0] if len(tied) == 1 else max(tied, key=lambda c: crime_cam[incident][c])

out = open(args.out, "w")
for key, s in sorted(spot.items()):
    label = tasks[key[0]]["label"]
    p = dict(s["predicted"] or {})
    if p.get("on_screen") in ("crime", "fleeing"):
        d = (describe.get(key) or {}).get("predicted") or {}
        for f in EXACT_FIELDS + TEXT_FIELDS:
            p[f] = d.get(f, "")  # a failed checker answer counts as wrong
    if p.get("on_screen") == "crime" and crime:
        c = ((crime.get(key) or {}).get("predicted") or {}).get("crime")
        if c in ("stabbing", "assault", "stealing"):
            p["crime"] = c  # checker "none" (can't tell) keeps the spotter's type
    if p.get("on_screen") == "crime" and (tasks[key[0]]["clip"], key[1]) in voted:
        p["crime"] = voted[(tasks[key[0]]["clip"], key[1])]
    checks = [float(p.get("on_screen") == label["on_screen"])]
    row = dict(on_screen_correct=checks[0], crime_correct=None, false_alarm=None, description_score=None)
    if label["on_screen"] == "crime":
        row["crime_correct"] = float(p.get("crime") == label["crime"]); checks.append(row["crime_correct"])
    if label["on_screen"] == "none":
        row["false_alarm"] = float(p.get("on_screen") == "crime"); checks.append(1 - row["false_alarm"])
    if label["on_screen"] in ("crime", "fleeing"):
        fields = [float(str(p.get(f, "")).lower() == label[f].lower()) for f in EXACT_FIELDS if is_scorable(label.get(f, ""))]
        fields += [float(text_match(label[f], str(p.get(f, "")))) for f in TEXT_FIELDS if is_scorable(label.get(f, ""))]
        if fields:
            row["description_score"] = sum(fields) / len(fields); checks.extend(fields)
    row.update(reward=sum(checks) / len(checks), answered=s["answered"], predicted=p,
               _ng_task_index=key[0], _ng_rollout_index=key[1])
    out.write(json.dumps(row) + "\n")
