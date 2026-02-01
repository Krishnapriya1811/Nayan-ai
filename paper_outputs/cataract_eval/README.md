# Cataract Results (Table I + Fig. 9)

This folder generates:
- **Table I – Cataract Screening Performance** (Accuracy, Precision, Recall, F1-score)
- **Fig. 9 – Confusion Matrix for Cataract Classification**

## What you need

1) The prediction log already in the repo:
- `backend/catract/cataract_dl_log.csv`

2) Ground-truth labels (you fill):
- `paper_outputs/cataract_eval/ground_truth_labels.csv`

The ground-truth CSV must have columns:
- `filename` (must match `upload_file` in the log)
- `true_label` (use exactly: `Normal` or `Possible Cataract Risk`)

## Run

From repo root:

```bat
D:\python\intepretor\Scripts\python.exe paper_outputs\cataract_eval\generate_table_I_and_fig9.py
```

## Outputs

Written to `paper_outputs/cataract_eval/outputs/`:
- `Table_I_Cataract_Screening_Performance.csv`
- `Table_I_Cataract_Screening_Performance.md`
- `confusion_matrix_values.csv`
- `Fig_9_Confusion_Matrix.png`

## First run behavior

If `ground_truth_labels.csv` does not exist, the script will **auto-create a template** with all filenames from the prediction log and exit. Fill `true_label` and re-run.
