"""Fix backend/catract/cataract_dl_log.csv into a clean RFC-4180 CSV.

This repo file sometimes gets appended with TAB-separated rows like:
  01-12-2025 9.00\teye_...jpg\tcataract\t0.83\t{"cataract": 0.83, "normal": 0.17}

This script:
- Creates a backup next to the file
- Normalizes all rows into 5 columns:
  timestamp, upload_file, pred_label, confidence, probs_json
- Normalizes timestamp to "YYYY-MM-DD HH:MM:SS" where possible

Run:
  D:/python/intepretor/Scripts/python.exe backend/catract/fix_cataract_dl_log.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path


HEADER = ["timestamp", "upload_file", "pred_label", "confidence", "probs_json"]


def _normalize_timestamp(value: str) -> str:
    s = str(value).strip()
    if not s:
        return s

    # ISO-like: 2025-12-29 17:04:45
    try:
        dt = datetime.fromisoformat(s)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # dd-mm-yyyy h.mm (day-first)
    # Example: 01-12-2025 9.00
    m = re.match(r"^(\d{2}-\d{2}-\d{4})\s+(.+)$", s)
    if m:
        date_part = m.group(1)
        time_part = m.group(2).strip()
        time_part = time_part.replace(".", ":")

        # Ensure seconds
        if time_part.count(":") == 0:
            time_part = f"{time_part}:00:00"
        elif time_part.count(":") == 1:
            time_part = f"{time_part}:00"

        # Zero-pad hour
        hh, mm, ss = time_part.split(":")
        hh = hh.zfill(2)
        mm = mm.zfill(2)
        ss = ss.zfill(2)

        dt = datetime.strptime(f"{date_part} {hh}:{mm}:{ss}", "%d-%m-%Y %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    # Fallback: return original
    return s


def _parse_line(line: str) -> tuple[str, str, str, float, str] | None:
    raw = line.strip("\n\r")
    if not raw.strip():
        return None

    if raw.startswith("timestamp,upload_file"):
        return None

    if "\t" in raw:
        # TAB-separated rows appended manually
        parts = [p.strip() for p in raw.split("\t")]
        parts = [p for p in parts if p != ""]
        if len(parts) < 5:
            return None
        ts, upload, pred, conf = parts[0], parts[1], parts[2], parts[3]
        probs = "\t".join(parts[4:]).strip()
    else:
        # CSV row (with quoted probs_json)
        try:
            parsed = next(csv.reader([raw]))
        except Exception:
            return None
        if len(parsed) < 5:
            return None
        ts, upload, pred, conf = parsed[0], parsed[1], parsed[2], parsed[3]
        probs = ",".join(parsed[4:]).strip()

    pred_norm = str(pred).strip().lower()
    if pred_norm not in {"normal", "cataract"}:
        return None

    try:
        conf_f = float(str(conf).strip())
    except Exception:
        return None

    probs_raw = str(probs).strip()

    # Normalize probs_json into compact JSON string
    try:
        probs_obj = json.loads(probs_raw)
        probs_norm = json.dumps(probs_obj, ensure_ascii=False)
    except Exception:
        # Last resort: keep as-is
        probs_norm = probs_raw

    return _normalize_timestamp(ts), str(upload).strip(), pred_norm, conf_f, probs_norm


def _next_backup_path(src: Path) -> Path:
    base = src.with_suffix(src.suffix + ".bak")
    if not base.exists():
        return base
    for i in range(1, 1000):
        candidate = src.with_suffix(src.suffix + f".bak{i}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("Too many backups exist")


def main() -> int:
    default_path = Path(__file__).resolve().parent / "cataract_dl_log.csv"
    in_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_path
    out_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else default_path

    if not in_path.exists():
        print(f"ERROR: Input not found: {in_path}")
        return 2

    raw_text = in_path.read_text(encoding="utf-8", errors="replace").splitlines()

    rows: list[tuple[str, str, str, float, str]] = []
    for line in raw_text:
        parsed = _parse_line(line)
        if parsed is None:
            # Ignore headers/blanks; count only truly non-empty junk
            if line.strip() and not line.startswith("timestamp,upload_file"):
                # Could be header variants; keep skip count minimal
                pass
            continue
        rows.append(parsed)

    if not rows:
        print("ERROR: No parsable rows found; file left unchanged.")
        return 2

    # Keep ALL rows (no dedup) and sort by timestamp when possible.
    def sort_key(r: tuple[str, str, str, float, str]):
        ts = r[0]
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return datetime.min

    cleaned = sorted(rows, key=sort_key)

    backup = _next_backup_path(out_path)
    backup.write_text("\n".join(raw_text) + "\n", encoding="utf-8")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(HEADER)
        for ts, upload, pred, conf, probs in cleaned:
            writer.writerow([ts, upload, pred, f"{conf:.6f}", probs])

    print(f"Backup written: {backup}")
    print(f"Fixed log written: {out_path}")
    print(f"Rows kept: {len(cleaned)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
