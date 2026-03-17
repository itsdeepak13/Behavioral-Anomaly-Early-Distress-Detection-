# Sentio Mind — Behavioral Anomaly & Early Distress Detection

Adds a proactive alert layer on top of existing Sentio Mind session exports. No video or camera code — reads daily JSON files, builds personal baselines, and flags 7 behavioral anomaly patterns.

---

## Files

| File | Purpose |
|------|---------|
| `solution.py` | Main detection script — run this |
| `generate_sample_data.py` | Creates `sample_data/` test data |
| `alert_feed.json` | Machine-readable alert output |
| `alert_digest.html` | Offline counsellor report with sparklines |

---

## Usage

```bash
# Step 1 — generate test data
python generate_sample_data.py

# Step 2 — run detection
python solution.py
```

Open `alert_digest.html` in any browser. No internet required.

> Windows only: If you get a `UnicodeEncodeError`, add `encoding="utf-8"` to both `open()` calls that write files in `solution.py`.

---

## Anomaly Types Detected

| Type | Trigger |
|------|---------|
| `SUDDEN_DROP` | Wellbeing drops ≥ 20 pts vs personal baseline |
| `SUSTAINED_LOW` | Wellbeing < 45 for 3+ consecutive days |
| `SOCIAL_WITHDRAWAL` | Social engagement drops ≥ 25 pts + gaze mostly downward |
| `HYPERACTIVITY_SPIKE` | Combined energy ≥ 40 pts above baseline |
| `REGRESSION` | 3+ day recovery streak, then drops > 15 pts in one day |
| `GAZE_AVOIDANCE` | Zero eye contact for 3+ consecutive days |
| `ABSENCE_FLAG` | Not detected for 2+ consecutive days |

Baseline = first 3 detected sessions per student. If baseline std > 15, drop threshold is relaxed by 50% to reduce false positives.

---

## Flask Endpoint

```python
from solution import create_flask_app
app = create_flask_app()
app.run(port=5001)   # GET /get_alerts → returns alert_feed.json
```

Zero changes to the existing analysis pipeline.

---

## Sample Data

4 students, 7–9 days each. Every anomaly type is demonstrated at least once.

| Student | Anomalies |
|---------|-----------|
| Aryan Sharma (STU001) | `SUDDEN_DROP`, `SUSTAINED_LOW` |
| Priya Nair (STU002) | `SOCIAL_WITHDRAWAL`, `GAZE_AVOIDANCE` |
| Rahul Verma (STU003) | `ABSENCE_FLAG`, `REGRESSION` |
| Kavya Reddy (STU004) | `HYPERACTIVITY_SPIKE` |
