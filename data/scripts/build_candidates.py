"""Build staged_clips.csv (unverified placeholders) and the fetch list from source research.

Every visual field is 'Unknown': nothing here was viewed. Fill from frames, then
split each clip's single TBD row into one row per person (P1, P2, ...).
"""
import csv
from pathlib import Path

COLS = ("clip_id,person_id,source_title,source_url,license,license_url,attribution,footage_type,activity,"
        "location_type,crime,crime_happens_on_cam,camera_count,timestamps,duration_s,verification_status,"
        "confidence,build,height,shirt,pants,shoes,glasses,headwear,hair,bag,weapon,changes_between_cams,"
        "person_of_interest_notes,local_path").split(",")

CAV = "https://homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/"
CAV_LIC = "CC BY-SA (version not stated on source page)"
CAV_ATTR = "EC Funded CAVIAR project/IST 2001 37540, http://homepages.inf.ed.ac.uk/rbf/CAVIAR/ (CC BY-SA)"
MEVA_S3 = "https://mevadata-public-01.s3.amazonaws.com/examples/videos/"
MEVA_LIC = "CC BY 4.0"
MEVA_LIC_URL = "https://mevadata.org/resources/MEVA-data-license.txt"
MEVA_ATTR = '"Multiview Extended Video with Activities" (MEVA) dataset by Kitware Inc., mevadata.org, CC BY 4.0'

# (clip_id, title, url, license, license_url, attribution, footage_type, activity, location_type, source_label_note)
CLIPS = [
    ("cav_fight_runaway1", "CAVIAR INRIA Fight_RunAway1", CAV + "Fight_RunAway1/Fight_RunAway1.mpg", CAV_LIC, CAV, CAV_ATTR,
     "dataset actors", "fistfight", "indoor entrance lobby (per source page)", "source label: fight, then one person runs away"),
    ("cav_fight_runaway2", "CAVIAR INRIA Fight_RunAway2", CAV + "Fight_RunAway2/Fight_RunAway2.mpg", CAV_LIC, CAV, CAV_ATTR,
     "dataset actors", "fistfight", "indoor entrance lobby (per source page)", "source label: fight, then one person runs away (separate take from RunAway1)"),
    ("cav_fight_onemandown", "CAVIAR INRIA Fight_OneManDown", CAV + "Fight_OneManDown/Fight_OneManDown.mpg", CAV_LIC, CAV, CAV_ATTR,
     "dataset actors", "fistfight", "indoor entrance lobby (per source page)", "source label: fight, one person left on floor"),
    ("cav_fight_chase", "CAVIAR INRIA Fight_Chase", CAV + "Fight_Chase/Fight_Chase.mpg", CAV_LIC, CAV, CAV_ATTR,
     "dataset actors", "fistfight", "indoor entrance lobby (per source page)", "source label: fight with chase"),
    ("meva_ex085_theft", "MEVA example ex085-theft", MEVA_S3 + "ex085-theft.mp4", MEVA_LIC, MEVA_LIC_URL, MEVA_ATTR,
     "dataset actors", "purse_snatch", "Unknown", "source label: person_steals_object (MEVA def: larceny of backpack/purse/luggage). Confirm it is a grab from a person, not an unattended item, before keeping as purse_snatch"),
    ("cav_walk1", "CAVIAR INRIA Walk1", CAV + "Walk1/Walk1.mpg", CAV_LIC, CAV, CAV_ATTR,
     "dataset actors", "none", "indoor entrance lobby (per source page)", "source label: walking"),
    ("cav_walk2", "CAVIAR INRIA Walk2", CAV + "Walk2/Walk2.mpg", CAV_LIC, CAV, CAV_ATTR,
     "dataset actors", "none", "indoor entrance lobby (per source page)", "source label: walking"),
    ("cav_meet_walktogether1", "CAVIAR INRIA Meet_WalkTogether1", CAV + "Meet_WalkTogether1/Meet_WalkTogether1.mpg", CAV_LIC, CAV, CAV_ATTR,
     "dataset actors", "none", "indoor entrance lobby (per source page)", "source label: people meet and walk together"),
    ("cav_browse1", "CAVIAR INRIA Browse1", CAV + "Browse1/Browse1.mpg", CAV_LIC, CAV, CAV_ATTR,
     "dataset actors", "none", "indoor entrance lobby (per source page)", "source label: browsing"),
    ("meva_ex007_embrace", "MEVA example ex007-embrace-interaction", MEVA_S3 + "ex007-embrace-interaction.mp4", MEVA_LIC, MEVA_LIC_URL, MEVA_ATTR,
     "dataset actors", "none", "Unknown", "source label: person_embraces_person (hug) - hard negative"),
    ("meva_ex050_talking", "MEVA example ex050-people-talking", MEVA_S3 + "ex050-people-talking.mp4", MEVA_LIC, MEVA_LIC_URL, MEVA_ATTR,
     "dataset actors", "none", "Unknown", "source label: person_talks_to_person - hard negative"),
]

U = "Unknown"
out = Path("data/training")
out.mkdir(parents=True, exist_ok=True)
with open(out / "staged_clips.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLS)
    w.writeheader()
    for cid, title, url, lic, lic_url, attr, ftype, act, loc, note in CLIPS:
        crime = "no" if act == "none" else "yes"
        w.writerow({
            "clip_id": cid, "person_id": "TBD", "source_title": title, "source_url": url, "license": lic,
            "license_url": lic_url, "attribution": attr, "footage_type": ftype, "activity": act,
            "location_type": loc, "crime": crime,
            "crime_happens_on_cam": "N/A" if crime == "no" else "Unclear",
            "camera_count": U, "timestamps": "Not reviewed", "duration_s": U,
            "verification_status": "unverified", "confidence": U,
            **{k: U for k in ("build", "height", "shirt", "pants", "shoes", "glasses", "headwear", "hair", "bag", "weapon")},
            "changes_between_cams": U,
            "person_of_interest_notes": note + ". NOT VIEWED - fill from frames.",
            "local_path": f"data/raw/training/{cid}{Path(url).suffix}",
        })
with open(out / "staged_clips_candidates.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["clip_id", "source_url", "download_url", "license", "license_url"])
    for cid, title, url, lic, lic_url, *_ in CLIPS:
        w.writerow([cid, url, url, lic, lic_url])
print(f"wrote {len(CLIPS)} clips")
