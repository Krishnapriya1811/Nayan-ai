"""Generate Table I (cataract metrics) and Fig. 9 (confusion matrix).

Data sources:
- Predictions: backend/catract/cataract_dl_log.csv (pred_label, confidence)
- Ground truth: paper_outputs/cataract_eval/ground_truth_labels.csv (you fill)

Outputs (written to paper_outputs/cataract_eval/outputs):
- Table_I_Cataract_Screening_Performance.csv
- Table_I_Cataract_Screening_Performance.md
- Fig_9_Confusion_Matrix.png
- confusion_matrix_values.csv

Usage:
  D:/python/intepretor/Scripts/python.exe paper_outputs/cataract_eval/generate_table_I_and_fig9.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix


def _repo_root() -> Path:
    # .../Nayan-ai/paper_outputs/cataract_eval/generate_table_I_and_fig9.py
    return Path(__file__).resolve().parents[2]


def _normalize_label(value: str) -> str:
    v = str(value).strip().lower()
    if v in {"normal", "no cataract", "healthy"}:
        return "Normal"
    if v in {
        "cataract",
        "possible cataract risk",
        "cataract risk",
        "risk",
        "positive",
        "1",
        "yes",
    }:
        return "Possible Cataract Risk"
    raise ValueError(f"Unrecognized label: {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Table I and Fig. 9 for cataract screening")
    parser.add_argument(
        "--autofill-missing",
        action="store_true",
        help="DEMO ONLY: auto-fill missing true labels from model predictions",
    )
    args = parser.parse_args()

    root = _repo_root()
    pred_log = root / "backend" / "catract" / "cataract_dl_log.csv"

    here = Path(__file__).resolve().parent
    gt_path = here / "ground_truth_labels.csv"
    out_dir = here / "outputs"

    if not pred_log.exists():
        print(f"ERROR: Predictions log not found: {pred_log}")
        return 2

    preds = pd.read_csv(pred_log)
    required_cols = {"upload_file", "pred_label"}
    missing = required_cols - set(preds.columns)
    if missing:
        print(f"ERROR: Missing columns in {pred_log.name}: {sorted(missing)}")
        print(f"Found columns: {list(preds.columns)}")
        return 2

    # Keep the most recent prediction per filename if duplicates exist.
    if "timestamp" in preds.columns:
        preds["timestamp"] = pd.to_datetime(preds["timestamp"], errors="coerce")
        preds = preds.sort_values("timestamp")
    preds = preds.drop_duplicates(subset=["upload_file"], keep="last")

    preds = preds.rename(columns={"upload_file": "filename"})
    preds["filename"] = preds["filename"].astype(str).str.strip()

    def read_ground_truth_mixed(path: Path) -> pd.DataFrame:
        # Supports either proper CSV or lines like: filename\tLabel
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        filenames: list[str] = []
        labels: list[str] = []
        for line in lines:
            if not line.strip():
                continue
            if line.lower().startswith("filename"):
                continue
            if "," in line:
                a, b = line.split(",", 1)
                filenames.append(a.strip())
                labels.append(b.strip())
            elif "\t" in line:
                parts = [p for p in line.split("\t") if p != ""]
                if len(parts) >= 2:
                    filenames.append(parts[0].strip())
                    labels.append(parts[1].strip())
        return pd.DataFrame({"filename": filenames, "true_label": labels})

    if not gt_path.exists():
        template = pd.DataFrame({"filename": preds["filename"].tolist(), "true_label": ""})
        template.to_csv(gt_path, index=False)
        print(
            "Created ground-truth template at:\n"
            f"  {gt_path}\n\n"
            "Fill the true_label column with: Normal OR Possible Cataract Risk\n"
            "Then re-run this script to generate Table I and Fig. 9."
        )
        return 0

    gt = read_ground_truth_mixed(gt_path)
    if gt.empty:
        template = pd.DataFrame({"filename": preds["filename"].tolist(), "true_label": ""})
        template.to_csv(gt_path, index=False)
        print(
            "Ground-truth file exists but is empty; wrote template at:\n"
            f"  {gt_path}\n\n"
            "Fill the true_label column with: Normal OR Possible Cataract Risk\n"
            "Then re-run this script to generate Table I and Fig. 9."
        )
        return 0

    if not {"filename", "true_label"}.issubset(gt.columns):
        print(f"ERROR: {gt_path} must contain columns: filename,true_label")
        return 2

    gt["filename"] = gt["filename"].astype(str).str.strip()
    gt["true_label"] = gt["true_label"].astype(str).fillna("").str.strip()

    # Expand ground-truth file to include ALL prediction filenames (preserving existing labels).
    gt_indexed = gt.drop_duplicates(subset=["filename"], keep="last").set_index("filename")
    all_files = pd.Index(preds["filename"].tolist(), name="filename")
    expanded = gt_indexed.reindex(all_files).reset_index()
    expanded["true_label"] = expanded["true_label"].fillna("")
    # Save normalized CSV (comma-separated) for future edits.
    expanded.to_csv(gt_path, index=False)

    merged = preds.merge(expanded, on="filename", how="inner")

    if merged.empty:
        print(
            "ERROR: No overlap between predictions and ground truth.\n"
            "Check that filenames in ground_truth_labels.csv match upload_file in cataract_dl_log.csv."
        )
        return 2

    missing_mask = merged["true_label"].isna() | (merged["true_label"].astype(str).str.strip() == "")
    missing_count = int(missing_mask.sum())
    if missing_count > 0 and not args.autofill_missing:
        print(
            "ERROR: Some true_label values are missing.\n"
            f"Please fill them in {gt_path}. Missing count: {missing_count}\n"
            "Tip: run with --autofill-missing for DEMO ONLY."
        )
        return 2

    if missing_count > 0 and args.autofill_missing:
        # DEMO ONLY: use predictions as labels (not valid ground truth).
        def pred_to_true(pred: str) -> str:
            return "Normal" if str(pred).strip().lower() == "normal" else "Possible Cataract Risk"

        merged.loc[missing_mask, "true_label"] = merged.loc[missing_mask, "pred_label"].map(pred_to_true)
        (out_dir / "EVAL_NOTE_AUTOFILLED_DEMO.txt").write_text(
            "DEMO ONLY: Missing true labels were auto-filled from model predictions.\n"
            "This is NOT a valid performance evaluation for a thesis/paper.\n",
            encoding="utf-8",
        )

    # Normalize labels to paper-friendly names.
    merged["y_true"] = merged["true_label"].map(_normalize_label)
    merged["y_pred"] = merged["pred_label"].map(_normalize_label)

    labels = ["Normal", "Possible Cataract Risk"]

    acc = float(accuracy_score(merged["y_true"], merged["y_pred"]))
    report = classification_report(
        merged["y_true"],
        merged["y_pred"],
        labels=labels,
        target_names=labels,
        digits=4,
        output_dict=True,
        zero_division=0,
    )

    # ---- Table I outputs ----
    table_rows = []
    for cls in labels:
        table_rows.append(
            {
                "Class": cls,
                "Precision": report[cls]["precision"],
                "Recall": report[cls]["recall"],
                "F1-score": report[cls]["f1-score"],
                "Support": report[cls]["support"],
            }
        )

    table_rows.append(
        {
            "Class": "Overall Accuracy",
            "Precision": "",
            "Recall": "",
            "F1-score": acc,
            "Support": int(report["accuracy"] * report["macro avg"]["support"]) if "macro avg" in report else "",
        }
    )

    for avg_name in ["macro avg", "weighted avg"]:
        if avg_name in report:
            table_rows.append(
                {
                    "Class": avg_name.title(),
                    "Precision": report[avg_name]["precision"],
                    "Recall": report[avg_name]["recall"],
                    "F1-score": report[avg_name]["f1-score"],
                    "Support": report[avg_name]["support"],
                }
            )

    table_df = pd.DataFrame(table_rows)

    csv_out = out_dir / "Table_I_Cataract_Screening_Performance.csv"
    md_out = out_dir / "Table_I_Cataract_Screening_Performance.md"

    table_df.to_csv(csv_out, index=False)

    # Markdown table formatting (4 decimals where numeric)
    md_df = table_df.copy()
    for col in ["Precision", "Recall", "F1-score"]:
        md_df[col] = md_df[col].apply(lambda x: f"{x:.4f}" if isinstance(x, (int, float)) else x)
    md_df["Support"] = md_df["Support"].apply(lambda x: f"{int(x)}" if isinstance(x, (int, float)) and x != "" else x)

    md_out.write_text(md_df.to_markdown(index=False), encoding="utf-8")

    # ---- Confusion matrix (Fig. 9) ----
    cm = confusion_matrix(merged["y_true"], merged["y_pred"], labels=labels)
    cm_df = pd.DataFrame(cm, index=[f"True: {l}" for l in labels], columns=[f"Pred: {l}" for l in labels])

    cm_csv = out_dir / "confusion_matrix_values.csv"
    cm_df.to_csv(cm_csv)

    plt.figure(figsize=(6.2, 5.2))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False,
                xticklabels=labels, yticklabels=labels)
    plt.xlabel("Predicted")
    plt.ylabel("True")
    plt.title("Fig. 9 – Confusion Matrix for Cataract Classification")
    plt.tight_layout()

    fig_out = out_dir / "Fig_9_Confusion_Matrix.png"
    plt.savefig(fig_out, dpi=300)
    plt.close()

    summary = (
        f"Total predictions (unique files): {len(preds)}\n"
        f"Total labels in ground_truth_labels.csv: {len(expanded)}\n"
        f"Used for evaluation (merged): {len(merged)}\n"
        f"Missing labels remaining: {0 if args.autofill_missing else missing_count}\n"
    )
    (out_dir / "EVAL_SUMMARY.txt").write_text(summary, encoding="utf-8")

    print("Generated outputs:")
    print(f"- {csv_out}")
    print(f"- {md_out}")
    print(f"- {cm_csv}")
    print(f"- {fig_out}")
    print(f"- {out_dir / 'EVAL_SUMMARY.txt'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
