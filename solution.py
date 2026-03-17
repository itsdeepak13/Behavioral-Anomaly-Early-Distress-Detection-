#!/usr/bin/env python3
"""
solution.py — Behavioral Anomaly & Early Distress Detection
Sentio Mind Proof of Concept

Reads daily session JSON exports from sample_data/, builds a personal
baseline per student, then checks for 7 behavioral anomaly patterns.
No video or camera code — pure analytics on top of the existing scoring pipeline.

Usage:
    python solution.py                 # reads ./sample_data by default
    python solution.py /path/to/data   # custom data directory

Outputs:
    alert_feed.json     — machine-readable alerts (served by /get_alerts)
    alert_digest.html   — offline counsellor report with sparklines
"""

import json
import os
import sys
import statistics
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Optional, List, Dict, Any, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Config — adjust these without touching the detection logic
# ──────────────────────────────────────────────────────────────────────────────

DATA_DIR  = Path("sample_data")
OUT_JSON  = Path("alert_feed.json")
OUT_HTML  = Path("alert_digest.html")

BASELINE_DAYS = 3  # how many days to use for the personal baseline

# All numeric thresholds in one dict — easier to audit and tune
T = {
    "sudden_drop_pts":       20,   # wellbeing drop vs baseline to flag
    "sustained_low_score":   45,   # wellbeing must stay below this
    "sustained_low_days":     3,   # for this many consecutive days
    "social_withdrawal_pts": 25,   # social_engagement drop vs baseline
    "hyperactivity_pts":     40,   # combined_energy spike above baseline
    "regression_drop_pts":   15,   # single-day drop after a recovery streak
    "regression_recovery":    3,   # min consecutive improving days before regression fires
    "gaze_avoidance_days":    3,   # consecutive days with zero eye contact
    "absence_days":           2,   # consecutive days where person was not detected
    "high_variance_std":     15,   # if baseline std > this, relax drop threshold by 50%
}

SEVERITY = {
    "SUDDEN_DROP":        "HIGH",
    "SUSTAINED_LOW":      "HIGH",
    "SOCIAL_WITHDRAWAL":  "MEDIUM",
    "HYPERACTIVITY_SPIKE":"MEDIUM",
    "REGRESSION":         "HIGH",
    "GAZE_AVOIDANCE":     "MEDIUM",
    "ABSENCE_FLAG":       "HIGH",
}

COUNSELLOR_NOTES = {
    "SUDDEN_DROP":
        "Schedule a same-day check-in. A sudden drop often signals an acute stressor.",
    "SUSTAINED_LOW":
        "Refer to counsellor — wellbeing has been critically low for 3+ consecutive days.",
    "SOCIAL_WITHDRAWAL":
        "Encourage peer interaction. Downward gaze combined with low engagement is a concern.",
    "HYPERACTIVITY_SPIKE":
        "Monitor informally. Could indicate anxiety, a manic episode, or positive excitement.",
    "REGRESSION":
        "Support plan needs revisiting — a recovery trend has reversed sharply.",
    "GAZE_AVOIDANCE":
        "3+ days of zero eye contact may signal social anxiety or significant distress.",
    "ABSENCE_FLAG":
        "Welfare check required. Student has not been detected for 2 or more days.",
}


# ──────────────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────────────

def load_sessions(data_dir: Path) -> Dict[str, List[Dict]]:
    """
    Reads all .json files from data_dir, groups them by person_id,
    and sorts each student's session list by date (oldest first).
    """
    if not data_dir.exists():
        print(f"[ERROR] Data directory not found: {data_dir.resolve()}")
        sys.exit(1)

    by_student: Dict[str, List[Dict]] = defaultdict(list)
    skipped = 0

    for fpath in sorted(data_dir.glob("*.json")):
        try:
            with open(fpath, "r") as fh:
                record = json.load(fh)
        except (json.JSONDecodeError, OSError) as err:
            print(f"  [WARN] {fpath.name}: {err} — skipping")
            skipped += 1
            continue

        pid = record.get("person_id")
        if not pid:
            print(f"  [WARN] {fpath.name} has no person_id — skipping")
            skipped += 1
            continue

        raw = record.get("date", "")
        try:
            record["_date"] = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print(f"  [WARN] {fpath.name} bad date '{raw}' — skipping")
            skipped += 1
            continue

        by_student[pid].append(record)

    for pid in by_student:
        by_student[pid].sort(key=lambda r: r["_date"])

    total = sum(len(v) for v in by_student.values())
    note = f" ({skipped} file(s) skipped)" if skipped else ""
    print(f"  Loaded {total} sessions across {len(by_student)} student(s){note}")

    return dict(by_student)


# ──────────────────────────────────────────────────────────────────────────────
# Baseline computation
# ──────────────────────────────────────────────────────────────────────────────

def compute_baseline(sessions: List[Dict]) -> Dict[str, Any]:
    """
    Personal baseline from the first BASELINE_DAYS *detected* sessions.
    If fewer detected days are available, uses all of them.
    Returns averages for wellbeing, social engagement, and combined energy,
    plus the wellbeing std dev (used to decide whether to loosen thresholds).
    """
    detected = [s for s in sessions if s.get("detected", True)]
    pool = detected[:BASELINE_DAYS] if len(detected) >= BASELINE_DAYS else detected

    if not pool:
        # shouldn't happen in normal data, but let's not crash
        return {
            "wellbeing_avg":  50.0, "wellbeing_std": 0.0,
            "social_avg":     50.0, "energy_avg":    70.0, "n": 0,
        }

    wb_vals  = [s["wellbeing_score"]              for s in pool]
    soc_vals = [s["social_engagement"]            for s in pool]
    eng_vals = [s["energy"]["combined_energy"]    for s in pool]

    wb_std = statistics.pstdev(wb_vals) if len(wb_vals) > 1 else 0.0

    return {
        "wellbeing_avg": round(statistics.mean(wb_vals), 2),
        "wellbeing_std": round(wb_std, 2),
        "social_avg":    round(statistics.mean(soc_vals), 2),
        "energy_avg":    round(statistics.mean(eng_vals), 2),
        "n": len(pool),
    }


def effective_drop_threshold(baseline: Dict) -> float:
    """
    Relaxes the sudden-drop threshold by 50% for students whose baseline
    is already highly variable (std > 15). Prevents false positives for
    naturally volatile scorers.
    """
    base = float(T["sudden_drop_pts"])
    if baseline["wellbeing_std"] > T["high_variance_std"]:
        return base * 1.5
    return base


# ──────────────────────────────────────────────────────────────────────────────
# Alert factory — keeps the alert dict structure consistent everywhere
# ──────────────────────────────────────────────────────────────────────────────

_alert_seq = [0]  # mutable counter shared across all detector calls in a run


def _alert(alert_type: str, session: Dict,
           baseline_val: Optional[float], current_val: float,
           delta: float, detail: str) -> Dict:
    _alert_seq[0] += 1
    bv = round(baseline_val, 2) if baseline_val is not None else None
    return {
        "alert_id":           f"ALT_{_alert_seq[0]:04d}",
        "person_id":          session["person_id"],
        "name":               session.get("name", session["person_id"]),
        "alert_type":         alert_type,
        "severity":           SEVERITY[alert_type],
        "triggered_on":       session["date"],
        "detail":             detail,
        "baseline_value":     bv,
        "current_value":      round(current_val, 2),
        "delta":              round(delta, 2),
        "recommended_action": COUNSELLOR_NOTES[alert_type],
    }


# ──────────────────────────────────────────────────────────────────────────────
# The 7 detectors
# ──────────────────────────────────────────────────────────────────────────────

def detect_sudden_drop(sessions: List[Dict], baseline: Dict) -> List[Dict]:
    """
    SUDDEN_DROP: wellbeing fell >= threshold points compared to the personal
    baseline in a single day's reading.
    """
    alerts = []
    thresh = effective_drop_threshold(baseline)
    avg = baseline["wellbeing_avg"]

    for s in sessions:
        if not s.get("detected", True):
            continue
        drop = avg - s["wellbeing_score"]
        if drop >= thresh:
            alerts.append(_alert(
                "SUDDEN_DROP", s,
                baseline_val=avg,
                current_val=s["wellbeing_score"],
                delta=round(-drop, 2),
                detail=(f"Wellbeing score {s['wellbeing_score']:.1f} is "
                        f"{drop:.1f} pts below personal baseline ({avg:.1f})")
            ))
    return alerts


def detect_sustained_low(sessions: List[Dict], baseline: Dict) -> List[Dict]:
    """
    SUSTAINED_LOW: wellbeing score stays below 45 for 3+ consecutive
    detected days. Alert fires once on the day the streak is confirmed.
    """
    alerts = []
    streak: List[Dict] = []

    for s in sessions:
        if not s.get("detected", True):
            streak = []
            continue

        if s["wellbeing_score"] < T["sustained_low_score"]:
            streak.append(s)
        else:
            streak = []

        if len(streak) == T["sustained_low_days"]:
            first = streak[0]
            alerts.append(_alert(
                "SUSTAINED_LOW", s,
                baseline_val=baseline["wellbeing_avg"],
                current_val=s["wellbeing_score"],
                delta=round(s["wellbeing_score"] - baseline["wellbeing_avg"], 2),
                detail=(f"Wellbeing below {T['sustained_low_score']} for "
                        f"{T['sustained_low_days']} consecutive days "
                        f"(since {first['date']})")
            ))
    return alerts


def detect_social_withdrawal(sessions: List[Dict], baseline: Dict) -> List[Dict]:
    """
    SOCIAL_WITHDRAWAL: social_engagement drops >= 25 pts from baseline
    AND gaze is predominantly downward (downward_ratio >= 0.5).
    Both conditions must hold on the same day.
    """
    alerts = []
    soc_avg = baseline["social_avg"]

    for s in sessions:
        if not s.get("detected", True):
            continue

        soc_drop = soc_avg - s["social_engagement"]
        downward_ratio = s.get("gaze", {}).get("downward_ratio", 0.0)

        if soc_drop >= T["social_withdrawal_pts"] and downward_ratio >= 0.5:
            alerts.append(_alert(
                "SOCIAL_WITHDRAWAL", s,
                baseline_val=soc_avg,
                current_val=s["social_engagement"],
                delta=round(-soc_drop, 2),
                detail=(f"Social engagement {s['social_engagement']:.1f} is "
                        f"{soc_drop:.1f} pts below baseline ({soc_avg:.1f}); "
                        f"gaze downward {downward_ratio*100:.0f}% of session")
            ))
    return alerts


def detect_hyperactivity_spike(sessions: List[Dict], baseline: Dict) -> List[Dict]:
    """
    HYPERACTIVITY_SPIKE: combined energy (movement + restlessness) is
    >= 40 points above the personal energy baseline.
    """
    alerts = []
    energy_avg = baseline["energy_avg"]

    for s in sessions:
        if not s.get("detected", True):
            continue
        energy_now = s.get("energy", {}).get("combined_energy", 0.0)
        spike = energy_now - energy_avg
        if spike >= T["hyperactivity_pts"]:
            alerts.append(_alert(
                "HYPERACTIVITY_SPIKE", s,
                baseline_val=energy_avg,
                current_val=energy_now,
                delta=round(spike, 2),
                detail=(f"Combined energy {energy_now:.1f} is {spike:.1f} pts "
                        f"above personal baseline ({energy_avg:.1f})")
            ))
    return alerts


def detect_regression(sessions: List[Dict], baseline: Dict) -> List[Dict]:
    """
    REGRESSION: the student was on a confirmed recovery streak
    (3+ consecutive detected days each higher than the previous), then
    drops more than 15 wellbeing points in a single day.
    """
    alerts = []
    detected = [s for s in sessions if s.get("detected", True)]
    min_rec = T["regression_recovery"]

    for i in range(min_rec, len(detected)):
        # the window we check for a recovery trend is the min_rec sessions before i
        window = detected[i - min_rec: i]
        recovering = all(
            window[j]["wellbeing_score"] < window[j + 1]["wellbeing_score"]
            for j in range(len(window) - 1)
        )
        if not recovering:
            continue

        prev = detected[i - 1]["wellbeing_score"]
        curr = detected[i]["wellbeing_score"]
        drop = prev - curr

        if drop > T["regression_drop_pts"]:
            alerts.append(_alert(
                "REGRESSION", detected[i],
                baseline_val=prev,
                current_val=curr,
                delta=round(-drop, 2),
                detail=(f"After {min_rec}+ days of recovery, wellbeing fell "
                        f"{drop:.1f} pts in a single day ({prev:.1f} → {curr:.1f})")
            ))
    return alerts


def detect_gaze_avoidance(sessions: List[Dict], baseline: Dict) -> List[Dict]:
    """
    GAZE_AVOIDANCE: eye_contact_ratio == 0.0 for 3 or more consecutive
    detected days. Alert fires on the day the streak is confirmed.
    """
    alerts = []
    streak: List[Dict] = []

    for s in sessions:
        if not s.get("detected", True):
            streak = []
            continue

        if s.get("gaze", {}).get("eye_contact_ratio", 1.0) == 0.0:
            streak.append(s)
        else:
            streak = []

        if len(streak) == T["gaze_avoidance_days"]:
            first = streak[0]
            alerts.append(_alert(
                "GAZE_AVOIDANCE", s,
                baseline_val=None,
                current_val=0.0,
                delta=0.0,
                detail=(f"Zero eye contact recorded for "
                        f"{T['gaze_avoidance_days']} consecutive days "
                        f"(starting {first['date']})")
            ))
    return alerts


def detect_absence_flag(sessions: List[Dict], baseline: Dict) -> List[Dict]:
    """
    ABSENCE_FLAG: detected == False for 2+ consecutive days.
    Alert fires on the second absent day. One alert per streak.
    """
    alerts = []
    streak: List[Dict] = []

    for s in sessions:
        if not s.get("detected", True):
            streak.append(s)
        else:
            streak = []

        if len(streak) == T["absence_days"]:
            first = streak[0]
            alerts.append(_alert(
                "ABSENCE_FLAG", streak[-1],
                baseline_val=None,
                current_val=0.0,
                delta=0.0,
                detail=(f"Student not detected on {T['absence_days']} "
                        f"consecutive days (from {first['date']})")
            ))
    return alerts


# ──────────────────────────────────────────────────────────────────────────────
# Detection runner — calls all detectors for every student
# ──────────────────────────────────────────────────────────────────────────────

DETECTORS = [
    detect_sudden_drop,
    detect_sustained_low,
    detect_social_withdrawal,
    detect_hyperactivity_spike,
    detect_regression,
    detect_gaze_avoidance,
    detect_absence_flag,
]


def run_detection(sessions_by_student: Dict[str, List[Dict]]
                  ) -> Tuple[List[Dict], Dict[str, Dict]]:
    _alert_seq[0] = 0   # reset counter for a clean run
    all_alerts: List[Dict] = []
    baselines: Dict[str, Dict] = {}

    for pid, sessions in sessions_by_student.items():
        bl = compute_baseline(sessions)
        baselines[pid] = bl
        student_alerts: List[Dict] = []

        for fn in DETECTORS:
            found = fn(sessions, bl)
            student_alerts.extend(found)

        if student_alerts:
            types = ", ".join(sorted(set(a["alert_type"] for a in student_alerts)))
            print(f"  {pid} ({sessions[0].get('name', pid)}): "
                  f"{len(student_alerts)} alert(s) — {types}")
        else:
            print(f"  {pid} ({sessions[0].get('name', pid)}): no alerts")

        all_alerts.extend(student_alerts)

    # sort by date first, then HIGH before MEDIUM
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    all_alerts.sort(key=lambda a: (a["triggered_on"], order.get(a["severity"], 9)))

    return all_alerts, baselines


# ──────────────────────────────────────────────────────────────────────────────
# JSON output  (alert_feed.json — consumed by /get_alerts)
# ──────────────────────────────────────────────────────────────────────────────

def write_alert_feed(alerts: List[Dict]) -> None:
    high   = sum(1 for a in alerts if a["severity"] == "HIGH")
    medium = sum(1 for a in alerts if a["severity"] == "MEDIUM")
    flagged = len(set(a["person_id"] for a in alerts))

    payload = {
        "schema_version": "1.0",
        "generated_at":   datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total_alerts":     len(alerts),
            "high_severity":    high,
            "medium_severity":  medium,
            "low_severity":     len(alerts) - high - medium,
            "students_flagged": flagged,
        },
        "alerts": alerts,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    print(f"\n  → {OUT_JSON}  ({len(alerts)} alerts, {flagged} students flagged)")


# ──────────────────────────────────────────────────────────────────────────────
# HTML report  (alert_digest.html — offline, no CDN)
# ──────────────────────────────────────────────────────────────────────────────

def _sparkline(values: List[float], width=130, height=34,
               line_color="#4f46e5",
               threshold: Optional[float] = None) -> str:
    """
    Returns a minimal inline SVG sparkline — no JavaScript, no external deps.
    Draws a polyline + an endpoint dot that turns red when the last value
    dips below `threshold`.
    """
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'

    pad = 4
    lo, hi = min(clean), max(clean)
    spread = (hi - lo) or 1.0

    def px(i: int) -> float:
        return pad + (i / (len(clean) - 1)) * (width - 2 * pad)

    def py(v: float) -> float:
        return (height - pad) - ((v - lo) / spread) * (height - 2 * pad)

    pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(clean))
    lx, ly = px(len(clean) - 1), py(clean[-1])

    is_low = threshold is not None and clean[-1] < threshold
    dot_fill = "#ef4444" if is_low else line_color

    dash_line = ""
    if threshold is not None and lo < threshold < hi:
        ty = py(threshold)
        dash_line = (
            f'<line x1="{pad}" y1="{ty:.1f}" '
            f'x2="{width - pad}" y2="{ty:.1f}" '
            f'stroke="#fca5a5" stroke-width="1" stroke-dasharray="3,2"/>'
        )

    return (
        f'<svg width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
        f'{dash_line}'
        f'<polyline points="{pts}" fill="none" stroke="{line_color}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{dot_fill}"/>'
        f'</svg>'
    )


def _badge(severity: str) -> str:
    styles = {
        "HIGH":   "background:#fef2f2;color:#dc2626;border:1px solid #fca5a5",
        "MEDIUM": "background:#fffbeb;color:#d97706;border:1px solid #fcd34d",
        "LOW":    "background:#f0fdf4;color:#16a34a;border:1px solid #86efac",
    }
    s = styles.get(severity, "")
    return (f'<span style="font-size:11px;font-weight:600;padding:2px 9px;'
            f'border-radius:9999px;white-space:nowrap;{s}">{severity}</span>')


def write_html_report(alerts: List[Dict],
                      sessions_by_student: Dict[str, List[Dict]]) -> None:
    # build wellbeing trends for sparklines
    trends: Dict[str, Dict] = {}
    for pid, sessions in sessions_by_student.items():
        trends[pid] = {
            "name":   sessions[0].get("name", pid),
            "dates":  [s["date"] for s in sessions],
            "scores": [s["wellbeing_score"] if s.get("detected", True) else None
                       for s in sessions],
        }

    alerts_by_pid: Dict[str, List[Dict]] = defaultdict(list)
    for a in alerts:
        alerts_by_pid[a["person_id"]].append(a)

    flagged_pids = sorted(alerts_by_pid.keys())
    high_count   = sum(1 for a in alerts if a["severity"] == "HIGH")
    med_count    = sum(1 for a in alerts if a["severity"] == "MEDIUM")
    gen_time     = datetime.now().strftime("%d %b %Y, %H:%M")

    # ── summary cards ────────────────────────────────────────────────────────
    card_style = ("flex:1;min-width:130px;background:#fff;border:1px solid #e5e7eb;"
                  "border-radius:10px;padding:16px 20px;text-align:center")

    summary_html = f"""
    <div style="display:flex;gap:14px;margin-bottom:28px;flex-wrap:wrap">
      <div style="{card_style}">
        <div style="font-size:34px;font-weight:700;color:#111827">{len(alerts)}</div>
        <div style="font-size:11px;color:#6b7280;margin-top:4px;text-transform:uppercase;letter-spacing:.5px">Total Alerts</div>
      </div>
      <div style="{card_style};background:#fef2f2;border-color:#fca5a5">
        <div style="font-size:34px;font-weight:700;color:#dc2626">{high_count}</div>
        <div style="font-size:11px;color:#dc2626;margin-top:4px;text-transform:uppercase;letter-spacing:.5px">High Severity</div>
      </div>
      <div style="{card_style};background:#fffbeb;border-color:#fcd34d">
        <div style="font-size:34px;font-weight:700;color:#d97706">{med_count}</div>
        <div style="font-size:11px;color:#d97706;margin-top:4px;text-transform:uppercase;letter-spacing:.5px">Medium Severity</div>
      </div>
      <div style="{card_style}">
        <div style="font-size:34px;font-weight:700;color:#374151">{len(flagged_pids)}</div>
        <div style="font-size:11px;color:#6b7280;margin-top:4px;text-transform:uppercase;letter-spacing:.5px">Students Flagged</div>
      </div>
      <div style="{card_style}">
        <div style="font-size:34px;font-weight:700;color:#374151">{len(sessions_by_student)}</div>
        <div style="font-size:11px;color:#6b7280;margin-top:4px;text-transform:uppercase;letter-spacing:.5px">Monitored</div>
      </div>
    </div>"""

    # ── per-student blocks ───────────────────────────────────────────────────
    student_blocks = ""

    for pid in flagged_pids:
        s_alerts = alerts_by_pid[pid]
        trend    = trends.get(pid, {})
        name     = trend.get("name", pid)
        scores   = trend.get("scores", [])

        worst = "HIGH" if any(a["severity"] == "HIGH" for a in s_alerts) else "MEDIUM"
        spark_color = "#dc2626" if worst == "HIGH" else "#d97706"
        spark = _sparkline(scores, line_color=spark_color, threshold=45)

        # rows for this student's alert table
        table_rows = ""
        for a in s_alerts:
            table_rows += f"""
              <tr style="border-top:1px solid #f3f4f6">
                <td style="padding:9px 14px;color:#374151;font-size:13px;white-space:nowrap">{a['triggered_on']}</td>
                <td style="padding:9px 14px;font-size:13px">
                  <code style="background:#f3f4f6;padding:2px 7px;border-radius:5px;
                               font-size:11.5px;color:#374151">{a['alert_type']}</code>
                </td>
                <td style="padding:9px 14px">{_badge(a['severity'])}</td>
                <td style="padding:9px 14px;color:#6b7280;font-size:12.5px;line-height:1.5">{a['detail']}</td>
                <td style="padding:9px 14px;color:#374151;font-size:12.5px;line-height:1.5">{a['recommended_action']}</td>
              </tr>"""

        header_bg = "#fff5f5" if worst == "HIGH" else "#fffdf0"

        student_blocks += f"""
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;
                    margin-bottom:20px;overflow:hidden;
                    box-shadow:0 1px 4px rgba(0,0,0,.06)">

          <!-- student header row -->
          <div style="display:flex;align-items:center;justify-content:space-between;
                      flex-wrap:wrap;gap:12px;
                      padding:16px 20px;border-bottom:1px solid #e5e7eb;
                      background:{header_bg}">
            <div style="display:flex;align-items:center;gap:10px">
              <div style="width:38px;height:38px;border-radius:50%;
                          background:{'#fef2f2' if worst=='HIGH' else '#fffbeb'};
                          border:2px solid {'#fca5a5' if worst=='HIGH' else '#fcd34d'};
                          display:flex;align-items:center;justify-content:center;
                          font-weight:700;font-size:15px;
                          color:{'#dc2626' if worst=='HIGH' else '#d97706'}">
                {name[0].upper()}
              </div>
              <div>
                <span style="font-size:16px;font-weight:600;color:#111827">{name}</span>
                <span style="font-size:12px;color:#9ca3af;margin-left:8px">{pid}</span>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:20px">
              <div>
                <div style="font-size:10px;color:#9ca3af;margin-bottom:3px;
                            text-transform:uppercase;letter-spacing:.5px">Wellbeing Trend</div>
                {spark}
              </div>
              <div style="text-align:center">
                <div style="font-size:26px;font-weight:700;
                            color:{'#dc2626' if worst=='HIGH' else '#d97706'}">
                  {len(s_alerts)}
                </div>
                <div style="font-size:10px;color:#9ca3af;
                            text-transform:uppercase;letter-spacing:.5px">Alert(s)</div>
              </div>
            </div>
          </div>

          <!-- alert table -->
          <table style="width:100%;border-collapse:collapse">
            <thead>
              <tr style="background:#f9fafb">
                <th style="padding:8px 14px;text-align:left;font-size:11px;
                           color:#9ca3af;font-weight:600;text-transform:uppercase;
                           letter-spacing:.5px">Date</th>
                <th style="padding:8px 14px;text-align:left;font-size:11px;
                           color:#9ca3af;font-weight:600;text-transform:uppercase;
                           letter-spacing:.5px">Type</th>
                <th style="padding:8px 14px;text-align:left;font-size:11px;
                           color:#9ca3af;font-weight:600;text-transform:uppercase;
                           letter-spacing:.5px">Severity</th>
                <th style="padding:8px 14px;text-align:left;font-size:11px;
                           color:#9ca3af;font-weight:600;text-transform:uppercase;
                           letter-spacing:.5px">Detail</th>
                <th style="padding:8px 14px;text-align:left;font-size:11px;
                           color:#9ca3af;font-weight:600;text-transform:uppercase;
                           letter-spacing:.5px">Recommended Action</th>
              </tr>
            </thead>
            <tbody>{table_rows}</tbody>
          </table>
        </div>"""

    no_alerts_msg = "" if student_blocks else (
        '<p style="color:#6b7280;font-style:italic">No anomalies detected in current data.</p>'
    )

    # ── full HTML ─────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sentio Mind — Counsellor Alert Digest</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                   "Helvetica Neue", Arial, sans-serif;
      background: #f3f4f6;
      color: #1f2937;
      padding: 28px 20px;
      line-height: 1.5;
    }}
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .no-print {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div style="max-width:980px;margin:0 auto">

    <!-- ── Page header ── -->
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;
                padding:22px 28px;margin-bottom:22px;
                display:flex;align-items:center;justify-content:space-between;
                flex-wrap:wrap;gap:12px;box-shadow:0 1px 4px rgba(0,0,0,.05)">
      <div>
        <div style="font-size:20px;font-weight:700;color:#111827;line-height:1.3">
          🧠&nbsp; Sentio Mind &mdash; Counsellor Alert Digest
        </div>
        <div style="font-size:13px;color:#6b7280;margin-top:5px">
          Behavioral anomaly report &bull; For welfare staff and counsellors only
        </div>
      </div>
      <div style="text-align:right">
        <div style="font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:.5px">Generated</div>
        <div style="font-size:13px;font-weight:500;color:#374151">{gen_time}</div>
      </div>
    </div>

    <!-- ── Summary cards ── -->
    {summary_html}

    <!-- ── Student alert blocks ── -->
    <div style="font-size:13px;font-weight:600;color:#6b7280;
                text-transform:uppercase;letter-spacing:.6px;margin-bottom:14px">
      Flagged Students
    </div>

    {student_blocks}
    {no_alerts_msg}

    <!-- ── Footer ── -->
    <div style="text-align:center;font-size:11px;color:#d1d5db;
                margin-top:36px;padding-top:18px;border-top:1px solid #e5e7eb">
      Sentio Mind Proof of Concept &nbsp;&bull;&nbsp;
      Auto-generated from session data &nbsp;&bull;&nbsp;
      Always verify alerts with direct observation before taking action
    </div>

  </div>
</body>
</html>"""

    with open(OUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"  → {OUT_HTML}")


# ──────────────────────────────────────────────────────────────────────────────
# Flask /get_alerts endpoint
# Drop this into the existing Sentio Mind server — zero changes to the
# analysis pipeline, just one new route.
# ──────────────────────────────────────────────────────────────────────────────

def create_flask_app(feed_path: Path = OUT_JSON):
    """
    Returns a Flask app (or None if Flask isn't installed) with a single
    GET /get_alerts endpoint that serves the pre-generated alert_feed.json.

    Usage in the main Sentio Mind server:
        from solution import create_flask_app
        alerts_bp = create_flask_app()
        main_app.register_blueprint(alerts_bp)   # or just run standalone
    """
    try:
        from flask import Flask, jsonify
    except ImportError:
        print("[WARN] Flask not installed — /get_alerts endpoint unavailable")
        return None

    app = Flask(__name__)

    @app.route("/get_alerts", methods=["GET"])
    def get_alerts():
        if not feed_path.exists():
            return jsonify({
                "error": "alert_feed.json not found",
                "hint":  "Run solution.py first to generate the alert feed"
            }), 404
        with open(feed_path, "r") as fh:
            data = json.load(fh)
        return jsonify(data)

    return app


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR

    print("\n" + "─" * 54)
    print("  Sentio Mind — Behavioral Anomaly Detection")
    print("─" * 54)
    print(f"\n  Data dir : {data_dir.resolve()}")
    print(f"  Baseline : first {BASELINE_DAYS} detected sessions per student\n")

    print("  Loading sessions...")
    sessions = load_sessions(data_dir)
    if not sessions:
        print("  [ERROR] No valid session files found.")
        sys.exit(1)

    print("\n  Running detectors...\n")
    alerts, _ = run_detection(sessions)

    total    = len(alerts)
    flagged  = len(set(a["person_id"] for a in alerts))
    high_n   = sum(1 for a in alerts if a["severity"] == "HIGH")

    print(f"\n  ── Results ────────────────────────────────────")
    print(f"     {total} alert(s) across {flagged} student(s)  "
          f"({high_n} HIGH severity)")
    print(f"  ───────────────────────────────────────────────\n")

    print("  Writing outputs...")
    write_alert_feed(alerts)
    write_html_report(alerts, sessions)

    print("\n  Done.")
    print("  Open alert_digest.html in a browser to review.\n")


if __name__ == "__main__":
    main()
