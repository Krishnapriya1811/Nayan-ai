import os
import json
from pathlib import Path

import numpy as np

# If you faced Windows Keras 3 overflow issues, keep this ON.
# Must be set before importing TensorFlow.
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import tensorflow as tf
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

PROJECT_DIR = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_DIR / "archive" / "processed_images"
TEST_DIR = DATA_ROOT / "test"

ARTIFACTS = PROJECT_DIR / "artifacts"
MODEL_KERAS = ARTIFACTS / "cataract_mobilenetv2.keras"
LABELS_PATH = ARTIFACTS / "labels.json"

IMG_SIZE = (224, 224)
BATCH_SIZE = 32

def main():
    if not TEST_DIR.exists():
        raise FileNotFoundError(f"Test directory not found: {TEST_DIR}")
    if not MODEL_KERAS.exists():
        raise FileNotFoundError(f"Model not found: {MODEL_KERAS} (train first)")
    if not LABELS_PATH.exists():
        raise FileNotFoundError(f"labels.json not found: {LABELS_PATH}")

    class_names = json.loads(LABELS_PATH.read_text())["class_names"]
    print("Class names:", class_names)
    print("Using TEST_DIR:", TEST_DIR)

    test_ds = tf.keras.utils.image_dataset_from_directory(
        str(TEST_DIR),
        labels="inferred",
        label_mode="int",
        image_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=False,
    )

    model = tf.keras.models.load_model(str(MODEL_KERAS))

    y_true, y_pred = [], []

    for images, labels in test_ds:
        probs = model.predict(images, verbose=0)
        preds = np.argmax(probs, axis=1)

        y_true.extend(labels.numpy().tolist())
        y_pred.extend(preds.tolist())

    print("\nAccuracy:", accuracy_score(y_true, y_pred))

    print("\nConfusion Matrix (rows=true, cols=pred):")
    print(confusion_matrix(y_true, y_pred))

    print("\nClassification Report:")
    print(classification_report(y_true, y_pred, target_names=class_names, digits=4))

if __name__ == "__main__":
    main()