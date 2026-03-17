#!/usr/bin/env python3
"""
Generates sample_data/ JSON files that mimic real Sentio Mind daily session output.
Each file = one student, one day. Run this once to populate sample_data/.
"""

import json
from pathlib import Path

OUT = Path("sample_data")
OUT.mkdir(exist_ok=True)


def session(person_id, name, date, detected,
            wb, social, eye_ratio, downward, movement, restless,
            emotions):
    combined = round(movement + restless, 1)
    total_frames = 320
    eye_frames = round(eye_ratio * total_frames)
    dominant = "downward" if downward >= 0.5 else "forward"

    base = {
        "session_id":   f"sess_{person_id}_{date.replace('-','')}",
        "person_id":    person_id,
        "name":         name,
        "date":         date,
        "timestamp":    f"{date}T09:10:00",
        "detected":     detected,
        "face_confidence": 0.93 if detected else 0.0,
    }

    if not detected:
        base.update({
            "wellbeing_score":   None,
            "social_engagement": None,
            "gaze":   {"eye_contact_frames": 0, "total_frames": total_frames,
                       "eye_contact_ratio": 0.0, "dominant_direction": "none",
                       "downward_ratio": 0.0},
            "energy": {"movement_score": 0.0, "restlessness_score": 0.0,
                       "combined_energy": 0.0},
            "emotions": {},
        })
        return base

    base.update({
        "wellbeing_score":   wb,
        "social_engagement": social,
        "gaze": {
            "eye_contact_frames":  eye_frames,
            "total_frames":        total_frames,
            "eye_contact_ratio":   round(eye_ratio, 3),
            "dominant_direction":  dominant,
            "downward_ratio":      round(downward, 3),
        },
        "energy": {
            "movement_score":     round(movement, 1),
            "restlessness_score": round(restless, 1),
            "combined_energy":    combined,
        },
        "emotions": emotions,
    })
    return base


# ─── Student data ─────────────────────────────────────────────────────────────
# Each tuple: (date, detected, wb, social, eye_ratio, downward, movement, restless, emotions)

STUDENTS = {

    # ── STU001 Aryan Sharma ─────────────────────────────────────────────────
    # Pattern: SUDDEN_DROP (day 5) → SUSTAINED_LOW (days 5-7)
    "STU001": {
        "name": "Aryan Sharma",
        "days": [
            ("2024-01-13", True,  74.0, 68.0, 0.450, 0.18, 52.3, 29.7,
             {"happy":0.38,"sad":0.10,"angry":0.05,"fear":0.03,"disgust":0.02,"surprise":0.08,"neutral":0.34}),
            ("2024-01-14", True,  76.0, 70.0, 0.480, 0.15, 49.5, 29.5,
             {"happy":0.41,"sad":0.08,"angry":0.04,"fear":0.02,"disgust":0.02,"surprise":0.09,"neutral":0.34}),
            ("2024-01-15", True,  72.0, 65.0, 0.430, 0.20, 55.1, 29.9,
             {"happy":0.35,"sad":0.12,"angry":0.05,"fear":0.04,"disgust":0.02,"surprise":0.07,"neutral":0.35}),
            # day 4: starting to slip
            ("2024-01-16", True,  68.0, 60.0, 0.380, 0.28, 50.8, 29.2,
             {"happy":0.28,"sad":0.18,"angry":0.06,"fear":0.05,"disgust":0.03,"surprise":0.06,"neutral":0.34}),
            # day 5: SUDDEN_DROP — wellbeing 74→43 = 31 pts
            ("2024-01-17", True,  43.0, 55.0, 0.300, 0.35, 45.0, 30.0,
             {"happy":0.12,"sad":0.32,"angry":0.08,"fear":0.10,"disgust":0.04,"surprise":0.04,"neutral":0.30}),
            # days 6,7: SUSTAINED_LOW (<45 for 3 consecutive)
            ("2024-01-18", True,  41.0, 48.0, 0.220, 0.42, 40.5, 29.5,
             {"happy":0.10,"sad":0.36,"angry":0.07,"fear":0.12,"disgust":0.05,"surprise":0.03,"neutral":0.27}),
            ("2024-01-19", True,  38.0, 44.0, 0.180, 0.50, 38.2, 29.8,
             {"happy":0.08,"sad":0.40,"angry":0.08,"fear":0.14,"disgust":0.05,"surprise":0.03,"neutral":0.22}),
        ]
    },

    # ── STU002 Priya Nair ───────────────────────────────────────────────────
    # Pattern: SOCIAL_WITHDRAWAL (day 4) → GAZE_AVOIDANCE (days 5-7, 3 consecutive zeros)
    "STU002": {
        "name": "Priya Nair",
        "days": [
            ("2024-01-13", True,  68.0, 72.0, 0.520, 0.15, 45.5, 29.5,
             {"happy":0.40,"sad":0.08,"angry":0.04,"fear":0.03,"disgust":0.01,"surprise":0.10,"neutral":0.34}),
            ("2024-01-14", True,  70.0, 74.0, 0.550, 0.12, 43.0, 29.0,
             {"happy":0.44,"sad":0.07,"angry":0.03,"fear":0.02,"disgust":0.01,"surprise":0.11,"neutral":0.32}),
            ("2024-01-15", True,  67.0, 70.0, 0.500, 0.18, 48.5, 29.5,
             {"happy":0.37,"sad":0.10,"angry":0.04,"fear":0.03,"disgust":0.02,"surprise":0.09,"neutral":0.35}),
            # day 4: SOCIAL_WITHDRAWAL — social 72→44 (drop=28 ≥ 25) + downward 0.72
            ("2024-01-16", True,  62.0, 44.0, 0.060, 0.72, 43.0, 27.0,
             {"happy":0.10,"sad":0.28,"angry":0.05,"fear":0.14,"disgust":0.03,"surprise":0.05,"neutral":0.35}),
            # days 5-7: GAZE_AVOIDANCE — eye_contact_ratio = 0.0
            ("2024-01-17", True,  60.0, 40.0, 0.000, 0.80, 41.5, 26.5,
             {"happy":0.08,"sad":0.30,"angry":0.05,"fear":0.16,"disgust":0.03,"surprise":0.04,"neutral":0.34}),
            ("2024-01-18", True,  57.0, 38.0, 0.000, 0.82, 40.0, 26.0,
             {"happy":0.07,"sad":0.32,"angry":0.06,"fear":0.17,"disgust":0.04,"surprise":0.03,"neutral":0.31}),
            ("2024-01-19", True,  55.0, 36.0, 0.000, 0.85, 38.8, 25.2,
             {"happy":0.06,"sad":0.34,"angry":0.06,"fear":0.18,"disgust":0.04,"surprise":0.03,"neutral":0.29}),
        ]
    },

    # ── STU003 Rahul Verma ──────────────────────────────────────────────────
    # Pattern: ABSENCE_FLAG (days 4-5) → REGRESSION (recovery then sharp drop on day 9)
    "STU003": {
        "name": "Rahul Verma",
        "days": [
            ("2024-01-13", True,  62.0, 58.0, 0.400, 0.22, 40.5, 29.5,
             {"happy":0.30,"sad":0.15,"angry":0.06,"fear":0.05,"disgust":0.02,"surprise":0.08,"neutral":0.34}),
            ("2024-01-14", True,  58.0, 55.0, 0.350, 0.25, 38.5, 29.5,
             {"happy":0.26,"sad":0.18,"angry":0.06,"fear":0.06,"disgust":0.03,"surprise":0.07,"neutral":0.34}),
            ("2024-01-15", True,  55.0, 52.0, 0.330, 0.28, 36.0, 29.0,
             {"happy":0.22,"sad":0.22,"angry":0.07,"fear":0.07,"disgust":0.03,"surprise":0.06,"neutral":0.33}),
            # days 4-5: ABSENT — ABSENCE_FLAG fires on day 5
            ("2024-01-16", False, None, None, 0.0, 0.0, 0.0, 0.0, {}),
            ("2024-01-17", False, None, None, 0.0, 0.0, 0.0, 0.0, {}),
            # days 6-8: gradual recovery (each day higher than previous detected)
            ("2024-01-18", True,  50.0, 46.0, 0.280, 0.30, 34.5, 25.5,
             {"happy":0.20,"sad":0.24,"angry":0.07,"fear":0.08,"disgust":0.03,"surprise":0.06,"neutral":0.32}),
            ("2024-01-19", True,  55.0, 50.0, 0.320, 0.26, 36.5, 26.5,
             {"happy":0.24,"sad":0.20,"angry":0.06,"fear":0.07,"disgust":0.03,"surprise":0.07,"neutral":0.33}),
            ("2024-01-20", True,  60.0, 54.0, 0.360, 0.22, 38.5, 28.5,
             {"happy":0.29,"sad":0.16,"angry":0.06,"fear":0.06,"disgust":0.02,"surprise":0.08,"neutral":0.33}),
            # day 9: REGRESSION — after 3 recovery days, drops 17 pts (60→43)
            ("2024-01-21", True,  43.0, 48.0, 0.300, 0.35, 36.0, 28.0,
             {"happy":0.12,"sad":0.30,"angry":0.08,"fear":0.12,"disgust":0.04,"surprise":0.04,"neutral":0.30}),
        ]
    },

    # ── STU004 Kavya Reddy ──────────────────────────────────────────────────
    # Pattern: HYPERACTIVITY_SPIKE (combined_energy baseline=72, spikes to 115 on day 5)
    "STU004": {
        "name": "Kavya Reddy",
        "days": [
            ("2024-01-13", True,  70.0, 65.0, 0.440, 0.20, 43.0, 29.0,
             {"happy":0.38,"sad":0.10,"angry":0.05,"fear":0.03,"disgust":0.02,"surprise":0.09,"neutral":0.33}),
            ("2024-01-14", True,  72.0, 67.0, 0.460, 0.18, 41.5, 28.5,
             {"happy":0.40,"sad":0.09,"angry":0.04,"fear":0.03,"disgust":0.01,"surprise":0.10,"neutral":0.33}),
            ("2024-01-15", True,  71.0, 66.0, 0.450, 0.19, 45.0, 29.0,
             {"happy":0.39,"sad":0.10,"angry":0.04,"fear":0.03,"disgust":0.02,"surprise":0.09,"neutral":0.33}),
            ("2024-01-16", True,  68.0, 63.0, 0.420, 0.22, 46.5, 28.5,
             {"happy":0.34,"sad":0.12,"angry":0.05,"fear":0.04,"disgust":0.02,"surprise":0.08,"neutral":0.35}),
            # day 5: HYPERACTIVITY_SPIKE — combined_energy=115 vs baseline 72 → delta=43
            ("2024-01-17", True,  66.0, 61.0, 0.400, 0.24, 75.5, 39.5,
             {"happy":0.28,"sad":0.10,"angry":0.12,"fear":0.08,"disgust":0.03,"surprise":0.15,"neutral":0.24}),
            ("2024-01-18", True,  67.0, 62.0, 0.410, 0.21, 73.0, 39.0,
             {"happy":0.29,"sad":0.10,"angry":0.11,"fear":0.07,"disgust":0.03,"surprise":0.14,"neutral":0.26}),
            ("2024-01-19", True,  69.0, 64.0, 0.430, 0.20, 69.5, 38.5,
             {"happy":0.32,"sad":0.10,"angry":0.10,"fear":0.06,"disgust":0.02,"surprise":0.12,"neutral":0.28}),
        ]
    },
}


# ─── Write files ──────────────────────────────────────────────────────────────

count = 0
for pid, info in STUDENTS.items():
    name = info["name"]
    for row in info["days"]:
        date, detected = row[0], row[1]
        if detected:
            wb, social, eye, down, mov, rest, emos = row[2:]
        else:
            wb = social = eye = down = mov = rest = None
            emos = {}

        rec = session(pid, name, date, detected,
                      wb, social, eye or 0.0, down or 0.0,
                      mov or 0.0, rest or 0.0, emos)

        fname = OUT / f"{pid}_{date}.json"
        with open(fname, "w") as f:
            json.dump(rec, f, indent=2)
        count += 1

print(f"Generated {count} session files in {OUT}/")
