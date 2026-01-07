import os
import json
from pathlib import Path

# Workaround for a known Windows issue in some Keras 3.x builds that can raise
# OverflowError during training. This must be set before importing TensorFlow.
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

# ---------- CONFIG ----------
PROJECT_DIR = Path(__file__).resolve().parent

# Folder containing: train/<class>/..., test/<class>/...
DATA_ROOT = PROJECT_DIR / "archive" / "processed_images"
TRAIN_DIR = DATA_ROOT / "train"

IMG_SIZE = (224, 224)
BATCH_SIZE = 32

EPOCHS_HEAD = 5          # train classification head
EPOCHS_FINE = 10         # fine-tune upper layers
LR_HEAD = 1e-3
LR_FINE = 1e-5

OUT_DIR = PROJECT_DIR / "artifacts"
MODEL_KERAS = str(OUT_DIR / "cataract_mobilenetv2.keras")  # primary
MODEL_H5 = str(OUT_DIR / "cataract_mobilenetv2.h5")        # secondary
LABELS_PATH = str(OUT_DIR / "labels.json")

OUT_DIR.mkdir(parents=True, exist_ok=True)

def make_datasets():
    if not TRAIN_DIR.exists():
        raise FileNotFoundError(
            "Training directory not found. "
            f"Expected: {TRAIN_DIR} (resolved from script location). "
            "If your dataset is elsewhere, update DATA_ROOT/TRAIN_DIR in the config section."
        )
    if not TRAIN_DIR.is_dir():
        raise NotADirectoryError(f"TRAIN_DIR is not a directory: {TRAIN_DIR}")

    print(f"Using TRAIN_DIR: {TRAIN_DIR}")
    train_ds = tf.keras.utils.image_dataset_from_directory(
        str(TRAIN_DIR),
        labels="inferred",
        label_mode="int",
        image_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=True,
        seed=123,
        validation_split=0.2,
        subset="training",
    )
    val_ds = tf.keras.utils.image_dataset_from_directory(
        str(TRAIN_DIR),
        labels="inferred",
        label_mode="int",
        image_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=True,
        seed=123,
        validation_split=0.2,
        subset="validation",
    )

    class_names = train_ds.class_names
    with open(LABELS_PATH, "w") as f:
        json.dump({"class_names": class_names}, f, indent=2)

    AUTOTUNE = tf.data.AUTOTUNE
    train_ds = train_ds.cache().prefetch(buffer_size=AUTOTUNE)
    val_ds = val_ds.cache().prefetch(buffer_size=AUTOTUNE)
    return train_ds, val_ds, class_names

def build_model(num_classes: int):
    aug = tf.keras.Sequential([
        layers.RandomFlip("horizontal"),
        layers.RandomRotation(0.05),
        layers.RandomZoom(0.1),
        layers.RandomContrast(0.15),
    ], name="augmentation")

    base = MobileNetV2(
        include_top=False,
        weights="imagenet",
        input_shape=(IMG_SIZE[0], IMG_SIZE[1], 3),
    )
    base.trainable = False

    inputs = layers.Input(shape=(IMG_SIZE[0], IMG_SIZE[1], 3))
    x = aug(inputs)
    x = preprocess_input(x)
    x = base(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)

    model = models.Model(inputs, outputs)
    return model, base

def main():
    train_ds, val_ds, class_names = make_datasets()
    num_classes = len(class_names)
    print("Classes:", class_names)

    model, base = build_model(num_classes)

    callbacks = [
        # Save best model in .keras (primary)
        tf.keras.callbacks.ModelCheckpoint(
            MODEL_KERAS, monitor="val_accuracy", save_best_only=True, verbose=1
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_accuracy", patience=4, restore_best_weights=True
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=2, verbose=1
        ),
    ]

    # ----- Phase 1: train classification head -----
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LR_HEAD),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        metrics=["accuracy"]
    )
    print("\n[Phase 1] Training classification head...")
    model.fit(train_ds, validation_data=val_ds, epochs=EPOCHS_HEAD, callbacks=callbacks)

    # ----- Phase 2: fine-tune last layers -----
    print("\n[Phase 2] Fine-tuning top base layers...")
    base.trainable = True
    fine_tune_at = len(base.layers) - 40
    for layer in base.layers[:fine_tune_at]:
        layer.trainable = False

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LR_FINE),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        metrics=["accuracy"]
    )
    model.fit(train_ds, validation_data=val_ds, epochs=EPOCHS_FINE, callbacks=callbacks)

    # Ensure the latest/best weights are saved
    model.save(MODEL_KERAS)
    print("\nSaved primary model:", MODEL_KERAS)

    # Export portability copy (.h5)
    model.save(MODEL_H5)
    print("Exported secondary model:", MODEL_H5)

    print("Saved labels:", LABELS_PATH)

if __name__ == "__main__":
    main()