import os
import time
import csv
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, request, render_template_string, send_from_directory

APP = Flask(__name__)

# ---------------- Paths / Config ----------------
PROJECT_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = PROJECT_DIR / "uploads_dryeye"
LOG_FILE = PROJECT_DIR / "dry_eye_log.csv"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Video processing config
MAX_VIDEO_SECONDS = 60          # we will analyze up to this much
TARGET_FPS = 15                 # downsample for speed
ROI_SCALE = 0.35                # center ROI scale (tune 0.25..0.45)

# Openness metric config
CANNY_LOW = 40
CANNY_HIGH = 120
SMOOTH_WINDOW = 7

# Blink detection thresholds (tune)
THRESH_K = 0.65                 # threshold = baseline * THRESH_K
MIN_BLINK_MS = 80
MAX_BLINK_MS = 350
REFRACTORY_MS = 250

# Dry eye decision thresholds (screening)
MIN_BLINKS_PER_MIN = 10
MAX_IBI_SECONDS = 10.0

HTML = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nayan-AI Dry Eye (Mobile Video Upload)</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 18px; }
    .card { padding: 14px; border: 1px solid #ddd; border-radius: 10px; margin-top: 12px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 700; }
    .ok { background: #e6ffed; color: #0f5132; border: 1px solid #badbcc; }
    .risk { background: #fff3cd; color: #664d03; border: 1px solid #ffecb5; }
  </style>
</head>
<body>
  <h2>Nayan-AI Dry Eye Screening (Mobile Video Upload)</h2>

  <div class="card">
    <form method="post" enctype="multipart/form-data">
      <p class="mono">Upload a 20–60 second eye video (MP4). Keep the eye centered and steady.</p>
      <input type="file" name="video" accept="video/*" capture="environment" required>
      <button type="submit">Upload & Analyze</button>
    </form>
    <p class="mono">
      Notes: Use stable lighting. Avoid extreme reflections. Try 30 seconds for faster results.
    </p>
  </div>

  {% if result %}
  <div class="card">
    <h3>Result</h3>
    {% if result.label == "Dry Eye Risk" %}
      <span class="badge risk">Dry Eye Risk</span>
    {% else %}
      <span class="badge ok">Normal</span>
    {% endif %}

    <p class="mono">
      duration_sec={{result.duration_sec}}<br>
      blink_count={{result.blink_count}}<br>
      blink_rate_bpm={{result.blink_rate_bpm}}<br>
      mean_ibi_sec={{result.mean_ibi_sec}}<br>
      max_ibi_sec={{result.max_ibi_sec}}<br>
      max_eye_open_sec={{result.max_eye_open_sec}}<br>
    </p>

    <details>
      <summary>Processing details</summary>
      <p class="mono">
        ROI_SCALE={{result.roi_scale}} TARGET_FPS={{result.target_fps}}<br>
        THRESH_K={{result.thresh_k}} MIN_BLINK_MS={{result.min_blink_ms}} MAX_BLINK_MS={{result.max_blink_ms}} REFRACTORY_MS={{result.refractory_ms}}<br>
        CANNY={{result.canny_low}}/{{result.canny_high}} SMOOTH_WINDOW={{result.smooth_window}}<br>
      </p>
    </details>

    <p class="mono">
      Saved: <a href="/uploads_dryeye/{{result.video_name}}">{{result.video_name}}</a>
    </p>
  </div>
  {% endif %}
</body>
</html>
"""

def ensure_csv():
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "timestamp",
                "video_file",
                "duration_sec",
                "blink_count",
                "blink_rate_bpm",
                "mean_ibi_sec",
                "max_ibi_sec",
                "max_eye_open_sec",
                "label",
                "roi_scale",
                "target_fps",
                "thresh_k",
                "min_blink_ms",
                "max_blink_ms",
                "refractory_ms",
                "canny_low",
                "canny_high",
                "smooth_window",
            ])

def center_roi(frame_bgr, scale=0.35):
    h, w = frame_bgr.shape[:2]
    rh, rw = int(h * scale), int(w * scale)
    y1 = (h - rh) // 2
    x1 = (w - rw) // 2
    roi = frame_bgr[y1:y1+rh, x1:x1+rw]
    return roi

def openness_metric(roi_bgr):
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, CANNY_LOW, CANNY_HIGH)
    return float(np.mean(edges > 0))  # 0..1

def moving_average(values, window):
    if len(values) == 0:
        return 0.0
    if len(values) < window:
        return float(np.mean(values))
    return float(np.mean(values[-window:]))

def analyze_video(video_path: Path):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Could not open uploaded video.")

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not src_fps or src_fps <= 1:
        src_fps = 30.0

    frame_step = max(1, int(round(src_fps / TARGET_FPS)))
    max_frames = int(MAX_VIDEO_SECONDS * TARGET_FPS)

    metrics = []
    smooth_hist = []
    baseline = None

    in_blink = False
    blink_start_ms = None
    last_blink_end_ms = -10**9
    blinks_end_times = []  # seconds in analysis timeline

    last_blink_time_sec = None
    max_ibi = 0.0
    sum_ibi = 0.0
    ibi_count = 0

    eye_open_start_sec = 0.0
    max_eye_open = 0.0

    frame_idx = 0
    kept_idx = 0
    t0 = time.time()

    # analysis timeline is based on kept frames at TARGET_FPS
    def now_sec_from_kept(k):
        return k / float(TARGET_FPS)

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1

        if (frame_idx % frame_step) != 0:
            continue

        # stop after max frames
        if kept_idx >= max_frames:
            break

        roi = center_roi(frame, scale=ROI_SCALE)
        m = openness_metric(roi)

        metrics.append(m)
        smooth = moving_average(metrics, SMOOTH_WINDOW)
        smooth_hist.append(smooth)

        if len(smooth_hist) > 30:
            baseline = float(np.median(smooth_hist))
        else:
            baseline = float(np.mean(smooth_hist))

        thr = baseline * THRESH_K

        # update max eye open duration
        now_sec = now_sec_from_kept(kept_idx)
        if not in_blink:
            open_dur = now_sec - eye_open_start_sec
            if open_dur > max_eye_open:
                max_eye_open = open_dur

        # blink state machine
        now_ms = int(now_sec * 1000)

        if not in_blink:
            if smooth < thr and (now_ms - last_blink_end_ms) > REFRACTORY_MS:
                in_blink = True
                blink_start_ms = now_ms
        else:
            if smooth >= thr:
                dur_ms = now_ms - blink_start_ms
                in_blink = False
                last_blink_end_ms = now_ms

                if MIN_BLINK_MS <= dur_ms <= MAX_BLINK_MS:
                    blinks_end_times.append(now_sec)

                    if last_blink_time_sec is not None:
                        ibi = now_sec - last_blink_time_sec
                        max_ibi = max(max_ibi, ibi)
                        sum_ibi += ibi
                        ibi_count += 1

                    last_blink_time_sec = now_sec
                    eye_open_start_sec = now_sec

        kept_idx += 1

    cap.release()

    duration_sec = kept_idx / float(TARGET_FPS) if kept_idx > 0 else 0.0
    blink_count = len(blinks_end_times)
    blink_rate_bpm = blink_count * (60.0 / max(duration_sec, 1e-6))
    mean_ibi = (sum_ibi / ibi_count) if ibi_count > 0 else 0.0

    risk = (blink_rate_bpm < MIN_BLINKS_PER_MIN) or (max_ibi > MAX_IBI_SECONDS)
    label = "Dry Eye Risk" if risk else "Normal"

    return {
        "duration_sec": duration_sec,
        "blink_count": blink_count,
        "blink_rate_bpm": blink_rate_bpm,
        "mean_ibi_sec": mean_ibi,
        "max_ibi_sec": max_ibi,
        "max_eye_open_sec": max_eye_open,
        "label": label,
    }

@APP.route("/", methods=["GET", "POST"])
def index():
    ensure_csv()
    result = None

    if request.method == "POST":
        if "video" not in request.files:
            return render_template_string(HTML, result=None)

        f = request.files["video"]
        if not f.filename:
            return render_template_string(HTML, result=None)

        ts = time.strftime("%Y%m%d_%H%M%S")
        video_name = f"dryeye_{ts}.mp4"
        video_path = UPLOAD_DIR / video_name
        f.save(str(video_path))

        try:
            out = analyze_video(video_path)
        except Exception as e:
            return f"Error analyzing video: {e}", 400

        # log
        with open(LOG_FILE, "a", newline="") as csvf:
            w = csv.writer(csvf)
            w.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                video_name,
                f"{out['duration_sec']:.3f}",
                out["blink_count"],
                f"{out['blink_rate_bpm']:.3f}",
                f"{out['mean_ibi_sec']:.3f}",
                f"{out['max_ibi_sec']:.3f}",
                f"{out['max_eye_open_sec']:.3f}",
                out["label"],
                f"{ROI_SCALE:.2f}",
                TARGET_FPS,
                f"{THRESH_K:.2f}",
                MIN_BLINK_MS,
                MAX_BLINK_MS,
                REFRACTORY_MS,
                CANNY_LOW,
                CANNY_HIGH,
                SMOOTH_WINDOW,
            ])

        result = {
            **out,
            "video_name": video_name,
            # echo config for UI
            "roi_scale": f"{ROI_SCALE:.2f}",
            "target_fps": TARGET_FPS,
            "thresh_k": f"{THRESH_K:.2f}",
            "min_blink_ms": MIN_BLINK_MS,
            "max_blink_ms": MAX_BLINK_MS,
            "refractory_ms": REFRACTORY_MS,
            "canny_low": CANNY_LOW,
            "canny_high": CANNY_HIGH,
            "smooth_window": SMOOTH_WINDOW,
        }

        # format floats nicely for display
        for k in ["duration_sec", "blink_rate_bpm", "mean_ibi_sec", "max_ibi_sec", "max_eye_open_sec"]:
            result[k] = f"{float(result[k]):.3f}"

    return render_template_string(HTML, result=result)

@APP.route("/uploads_dryeye/<path:filename>")
def uploads(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)

if __name__ == "__main__":
    # Access from phone: http://<laptop-ip>:5000
    APP.run(host="0.0.0.0", port=5000, debug=False)