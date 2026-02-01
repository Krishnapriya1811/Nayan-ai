import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _fmt_mean_std(values: List[float], digits: int = 2) -> str:
    values = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not values:
        return "--"
    if len(values) == 1:
        return f"{values[0]:.{digits}f}"
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1))
    return f"{mean:.{digits}f} ± {std:.{digits}f}"


def _read_dry_eye_log(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Dry eye log not found: {csv_path}")

    df = pd.read_csv(csv_path)
    # Normalize label names
    if "label" not in df.columns:
        raise ValueError(f"Expected a 'label' column in {csv_path}")

    df["label"] = df["label"].astype(str).str.strip()

    # Ensure numeric columns are numeric
    numeric_cols = [
        "duration_sec",
        "blink_count",
        "blink_rate_bpm",
        "mean_ibi_sec",
        "max_ibi_sec",
        "max_eye_open_sec",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def generate_table_ii(df: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    # We only compare these two groups for the paper table.
    groups = {
        "Normal": df[df["label"].str.lower() == "normal"],
        "Dry Eye Risk": df[df["label"].str.lower() == "dry eye risk"],
    }

    rows = []
    metrics = [
        ("N", None, 0),
        ("Duration (s)", "duration_sec", 2),
        ("Blink Count", "blink_count", 0),
        ("Blink Rate (BPM)", "blink_rate_bpm", 2),
        ("Mean Inter-Blink Interval (s)", "mean_ibi_sec", 2),
        ("Max Inter-Blink Interval (s)", "max_ibi_sec", 2),
        ("Max Eye-Open Duration (s)", "max_eye_open_sec", 2),
    ]

    for metric_name, col, digits in metrics:
        row: Dict[str, object] = {"Metric": metric_name}
        for gname, gdf in groups.items():
            if metric_name == "N":
                row[gname] = int(len(gdf))
            else:
                if col not in gdf.columns:
                    row[gname] = "--"
                else:
                    row[gname] = _fmt_mean_std(gdf[col].dropna().tolist(), digits=digits)
        rows.append(row)

    out_df = pd.DataFrame(rows, columns=["Metric", "Normal", "Dry Eye Risk"])

    # For a short results paragraph
    summary_lines = []
    n_normal = int(len(groups["Normal"]))
    n_risk = int(len(groups["Dry Eye Risk"]))
    summary_lines.append(f"Normal samples: {n_normal}")
    summary_lines.append(f"Dry Eye Risk samples: {n_risk}")

    if n_normal > 0 and n_risk > 0 and "blink_rate_bpm" in df.columns:
        bn = groups["Normal"]["blink_rate_bpm"].dropna().tolist()
        br = groups["Dry Eye Risk"]["blink_rate_bpm"].dropna().tolist()
        if bn and br:
            summary_lines.append(f"Blink rate (BPM) Normal: {_fmt_mean_std(bn, 2)}")
            summary_lines.append(f"Blink rate (BPM) Risk: {_fmt_mean_std(br, 2)}")

    if n_normal > 0 and n_risk > 0 and "max_eye_open_sec" in df.columns:
        on = groups["Normal"]["max_eye_open_sec"].dropna().tolist()
        orisk = groups["Dry Eye Risk"]["max_eye_open_sec"].dropna().tolist()
        if on and orisk:
            summary_lines.append(f"Max eye-open (s) Normal: {_fmt_mean_std(on, 2)}")
            summary_lines.append(f"Max eye-open (s) Risk: {_fmt_mean_std(orisk, 2)}")

    return out_df, "\n".join(summary_lines)


@dataclass
class TraceResult:
    time_sec: np.ndarray
    openness_raw: np.ndarray
    openness_smooth: np.ndarray
    thr: np.ndarray
    blink_end_times_sec: List[float]


def _import_cv2():
    try:
        import cv2  # type: ignore

        return cv2
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "OpenCV (cv2) is required to generate Fig. 10, but it could not be imported. "
            "Install opencv-python and try again."
        ) from e


def analyze_video_with_trace(
    video_path: Path,
    *,
    max_video_seconds: int = 60,
    target_fps: int = 15,
    roi_scale: float = 0.35,
    canny_low: int = 40,
    canny_high: int = 120,
    smooth_window: int = 7,
    thresh_k: float = 0.65,
    min_blink_ms: int = 80,
    max_blink_ms: int = 350,
    refractory_ms: int = 250,
) -> TraceResult:
    cv2 = _import_cv2()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not src_fps or src_fps <= 1:
        src_fps = 30.0

    frame_step = max(1, int(round(src_fps / target_fps)))
    max_frames = int(max_video_seconds * target_fps)

    def center_roi(frame_bgr):
        h, w = frame_bgr.shape[:2]
        rh, rw = int(h * roi_scale), int(w * roi_scale)
        y1 = (h - rh) // 2
        x1 = (w - rw) // 2
        return frame_bgr[y1 : y1 + rh, x1 : x1 + rw]

    def openness_metric(roi_bgr) -> float:
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, canny_low, canny_high)
        return float(np.mean(edges > 0))  # 0..1

    def moving_average(values: List[float], window: int) -> float:
        if len(values) == 0:
            return 0.0
        if len(values) < window:
            return float(np.mean(values))
        return float(np.mean(values[-window:]))

    metrics: List[float] = []
    smooth_hist: List[float] = []
    thr_hist: List[float] = []

    in_blink = False
    blink_start_ms: Optional[int] = None
    last_blink_end_ms = -10**9
    blinks_end_times: List[float] = []

    frame_idx = 0
    kept_idx = 0

    def now_sec_from_kept(k: int) -> float:
        return k / float(target_fps)

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1

        if (frame_idx % frame_step) != 0:
            continue

        if kept_idx >= max_frames:
            break

        roi = center_roi(frame)
        m = openness_metric(roi)
        metrics.append(m)

        smooth = moving_average(metrics, smooth_window)
        smooth_hist.append(smooth)

        if len(smooth_hist) > 30:
            baseline = float(np.median(smooth_hist))
        else:
            baseline = float(np.mean(smooth_hist))

        thr = baseline * float(thresh_k)
        thr_hist.append(thr)

        now_sec = now_sec_from_kept(kept_idx)
        now_ms = int(now_sec * 1000)

        if not in_blink:
            if smooth < thr and (now_ms - last_blink_end_ms) > int(refractory_ms):
                in_blink = True
                blink_start_ms = now_ms
        else:
            if smooth >= thr:
                dur_ms = now_ms - int(blink_start_ms or now_ms)
                in_blink = False
                last_blink_end_ms = now_ms

                if int(min_blink_ms) <= dur_ms <= int(max_blink_ms):
                    blinks_end_times.append(now_sec)

        kept_idx += 1

    cap.release()

    t = np.arange(len(metrics), dtype=float) / float(target_fps)
    return TraceResult(
        time_sec=t,
        openness_raw=np.asarray(metrics, dtype=float),
        openness_smooth=np.asarray(smooth_hist, dtype=float),
        thr=np.asarray(thr_hist, dtype=float),
        blink_end_times_sec=blinks_end_times,
    )


def write_markdown_table(table_df: pd.DataFrame, out_path: Path) -> None:
    header = "| " + " | ".join(table_df.columns) + " |"
    sep = "|" + "|".join(["---"] * len(table_df.columns)) + "|"
    lines = [header, sep]
    for _, row in table_df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in table_df.columns) + " |")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Table II (Dry Eye blink metrics) and Fig. 10 (eye openness signal with detected blinks)."
    )
    parser.add_argument(
        "--log",
        type=str,
        default=str(Path("backend/dryeye/dry_eye_log.csv")),
        help="Path to backend/dryeye/dry_eye_log.csv",
    )
    parser.add_argument(
        "--video",
        type=str,
        default="",
        help="Optional: path to a dry-eye video file to use for Fig. 10. If omitted, will pick the most recent logged video that exists.",
    )
    parser.add_argument(
        "--outputs",
        type=str,
        default=str(Path("paper_outputs/dryeye_eval/outputs")),
        help="Output directory",
    )

    args = parser.parse_args()

    log_path = Path(args.log)
    out_dir = Path(args.outputs)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _read_dry_eye_log(log_path)

    table_df, summary_text = generate_table_ii(df)

    table_csv = out_dir / "Table_II_Blink_Metrics_Normal_vs_DryEyeRisk.csv"
    table_md = out_dir / "Table_II_Blink_Metrics_Normal_vs_DryEyeRisk.md"
    table_df.to_csv(table_csv, index=False)
    write_markdown_table(table_df, table_md)

    # Choose video for Fig. 10
    chosen_video: Optional[Path] = None
    if args.video:
        chosen_video = Path(args.video)
    else:
        # Most recent row in log where the file exists.
        # Videos may live in either backend/dryeye/uploads_dryeye (mobile_dry_eye_server.py)
        # or uploads/dryeye (backend/app.py route).
        if "video_file" in df.columns:
            search_dirs = [
                log_path.parent / "uploads_dryeye",
                Path("uploads") / "dryeye",
                log_path.parent,
            ]
            for v in reversed(df["video_file"].astype(str).tolist()):
                v = v.strip()
                if not v:
                    continue
                for d in search_dirs:
                    candidate = d / v
                    if candidate.exists():
                        chosen_video = candidate
                        break
                if chosen_video is not None:
                    break

    fig10_png = out_dir / "Fig_10_Eye_Openness_Signal_With_Detected_Blinks.png"
    fig10_csv = out_dir / "Fig_10_Eye_Openness_Signal_With_Detected_Blinks.csv"

    fig10_note = ""
    if chosen_video is None or not chosen_video.exists():
        fig10_note = (
            "Fig. 10 was not generated because no existing video file was found. "
            "Pass --video <path-to-mp4> to generate it."
        )
    else:
        trace = analyze_video_with_trace(chosen_video)

        # Save underlying data for reproducibility
        signal_df = pd.DataFrame(
            {
                "time_sec": trace.time_sec,
                "openness_raw": trace.openness_raw,
                "openness_smooth": trace.openness_smooth,
                "threshold": trace.thr,
            }
        )
        signal_df.to_csv(fig10_csv, index=False)

        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.figure(figsize=(10, 4))
        plt.plot(trace.time_sec, trace.openness_smooth, label="Smoothed openness", linewidth=2)
        plt.plot(trace.time_sec, trace.openness_raw, label="Raw openness", alpha=0.35, linewidth=1)
        plt.plot(trace.time_sec, trace.thr, label="Blink threshold", linestyle="--", linewidth=1)

        for t_b in trace.blink_end_times_sec:
            plt.axvline(t_b, color="red", alpha=0.25, linewidth=1)

        plt.title("Eye Openness Signal with Detected Blinks")
        plt.xlabel("Time (s)")
        plt.ylabel("Openness (0–1)")
        plt.legend(loc="upper right")
        plt.tight_layout()
        plt.savefig(fig10_png, dpi=200)
        plt.close()

        fig10_note = f"Fig. 10 generated using video: {chosen_video} (detected blinks: {len(trace.blink_end_times_sec)})"

    summary_path = out_dir / "DRYEYE_EVAL_SUMMARY.txt"
    summary_path.write_text(
        "\n".join(
            [
                "Dry Eye Screening Outputs",
                "=========================",
                f"Log: {log_path}",
                f"Rows in log: {len(df)}",
                "",
                "Table II:",
                f"- {table_csv}",
                f"- {table_md}",
                "",
                "Fig. 10:",
                f"- {fig10_png}",
                f"- {fig10_csv}",
                "",
                "Quick summary:",
                summary_text,
                "",
                fig10_note,
            ]
        ),
        encoding="utf-8",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
