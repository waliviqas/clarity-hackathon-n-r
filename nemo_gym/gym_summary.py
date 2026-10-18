import json, sys
def summary(path):
    rows = [json.loads(l) for l in open(path)]
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 3) if xs else None
    return dict(runs=len(rows), reward=mean([r["reward"] for r in rows]),
                on_screen=mean([r["on_screen_correct"] for r in rows]),
                crime_type=mean([r["crime_correct"] for r in rows]),
                false_alarm=mean([r["false_alarm"] for r in rows]),
                description=mean([r["description_score"] for r in rows]),
                answered=sum(r["answered"] for r in rows))
names = sys.argv[1::2]; paths = sys.argv[2::2]
s = [summary(p) for p in paths]
print(f"{'':12}" + "".join(f"{n:>10}" for n in names))
for k in s[0]:
    print(f"{k:12}" + "".join(f"{x[k]!s:>10}" for x in s))
