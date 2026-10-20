"""
utils.py
Shared helper functions for the Face Recognition Door project.

Handles:
- Folder / path setup
- Reading the registered-user dataset
- Training the LBPH face recognizer
- Loading the trained model + label map
"""

import os
import pickle
import re

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
TRAINER_DIR = os.path.join(BASE_DIR, "trainer")
MODEL_PATH = os.path.join(TRAINER_DIR, "trainer.yml")
LABELS_PATH = os.path.join(TRAINER_DIR, "labels.pickle")
CASCADE_PATH = os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml")

FACE_SIZE = (200, 200)          # every saved/trained face is resized to this
IMAGES_PER_USER = 10            # 10 samples = much more stable LBPH matching
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
# Lower number = stricter match. LBPH "confidence" is actually a distance,
# so SMALLER values mean a BETTER match. Anything above this is "unknown".
# 50 is strict enough to block unknown faces but still matches registered users.
RECOGNITION_THRESHOLD = 50

# Ask the webcam for 720p so distant faces stay large enough to recognize.
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720

# Haar detection tuned for range: smaller scaleFactor finds distant faces,
# lower minNeighbors misses fewer real faces (multi-frame voting absorbs noise).
DETECT_SCALE_FACTOR = 1.1
DETECT_MIN_NEIGHBORS = 4
DETECT_MIN_SIZE = (40, 40)

# Registration quality gate: only save samples where the face is at least
# this wide (at 720p) so every stored image is sharp and well-framed.
MIN_FACE_PX = 90

# Bump when the train/predict preprocessing changes so old models retrain.
PIPELINE_VERSION = "2-clahe"
VERSION_PATH = os.path.join(TRAINER_DIR, "pipeline.txt")

_clahe = None


def get_clahe():
    """Single shared CLAHE instance (local-contrast normalization for lighting)."""
    global _clahe
    if _clahe is None:
        _clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return _clahe


def preprocess(gray):
    """Shared train/predict preprocessing: resize to FACE_SIZE + CLAHE."""
    if gray is None or gray.size == 0:
        return None
    if gray.shape[:2] != (FACE_SIZE[1], FACE_SIZE[0]):
        gray = cv2.resize(gray, FACE_SIZE, interpolation=cv2.INTER_AREA)
    return get_clahe().apply(gray)


def open_camera(index=0):
    """Open webcam and request the highest useful resolution."""
    cap = cv2.VideoCapture(index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    return cap


def detect_faces(detector, gray):
    """
    Detect faces on a full-resolution frame.
    If nothing is found, retry on an upscaled copy — this is what
    lets the scanner see faces that are farther from the camera.
    Boxes are returned in original-frame coordinates.
    """
    faces = detector.detectMultiScale(
        gray,
        scaleFactor=DETECT_SCALE_FACTOR,
        minNeighbors=DETECT_MIN_NEIGHBORS,
        minSize=DETECT_MIN_SIZE,
    )
    if len(faces) == 0:
        h, w = gray.shape[:2]
        if w < 1600:  # don't blow up already-large frames
            big = cv2.resize(gray, (w * 3 // 2, h * 3 // 2), interpolation=cv2.INTER_CUBIC)
            found = detector.detectMultiScale(
                big,
                scaleFactor=DETECT_SCALE_FACTOR,
                minNeighbors=DETECT_MIN_NEIGHBORS,
                minSize=(DETECT_MIN_SIZE[0] * 3 // 2, DETECT_MIN_SIZE[1] * 3 // 2),
            )
            if len(found) > 0:
                faces = [(int(x * 2 / 3), int(y * 2 / 3), int(fw * 2 / 3), int(fh * 2 / 3))
                         for (x, y, fw, fh) in found]
    return faces


def ensure_dirs():
    os.makedirs(DATASET_DIR, exist_ok=True)
    os.makedirs(TRAINER_DIR, exist_ok=True)


def normalize_user_name(name):
    """Return a filesystem-safe user name and trim whitespace."""
    safe_name = re.sub(r"\s+", " ", name.strip())
    safe_name = "".join(ch for ch in safe_name if ch.isalnum() or ch in (" ", "_", "-"))
    return safe_name.strip()


def user_image_count(user_dir):
    if not os.path.isdir(user_dir):
        return 0
    return sum(
        1 for file_name in os.listdir(user_dir)
        if file_name.lower().endswith(IMAGE_EXTENSIONS)
    )


def get_face_detector():
    detector = cv2.CascadeClassifier(CASCADE_PATH)
    if detector.empty():
        raise RuntimeError(
            f"Could not load Haar Cascade file at {CASCADE_PATH}. "
            "Make sure haarcascade_frontalface_default.xml is in the project folder."
        )
    return detector


def list_registered_users():
    """Return a sorted list of user names that already have a dataset folder."""
    ensure_dirs()
    return sorted(
        name for name in os.listdir(DATASET_DIR)
        if os.path.isdir(os.path.join(DATASET_DIR, name))
    )


def user_dataset_path(name):
    return os.path.join(DATASET_DIR, name)


def train_model():
    """
    Reads every image under dataset/<user_name>/*.jpg, trains an LBPH
    face recognizer, and saves the model + the label<->name mapping.

    Returns (num_users, num_images) trained on.
    """
    ensure_dirs()
    recognizer = cv2.face.LBPHFaceRecognizer_create()

    faces = []
    labels = []
    label_to_name = {}
    current_label = 0

    users = list_registered_users()
    if not users:
        raise ValueError("No registered users found. Register at least one face first.")

    for user_name in users:
        user_dir = user_dataset_path(user_name)
        image_files = sorted(
            f for f in os.listdir(user_dir)
            if f.lower().endswith(IMAGE_EXTENSIONS)
        )
        if not image_files:
            continue

        # Collect valid images first; only assign a label if at least one loaded
        user_faces = []
        for image_file in image_files:
            img_path = os.path.join(user_dir, image_file)
            gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                continue
            processed = preprocess(gray)
            if processed is None:
                continue
            user_faces.append(processed)

        if not user_faces:
            continue  # skip users with no usable images

        label_to_name[current_label] = user_name
        for face in user_faces:
            faces.append(face)
            labels.append(current_label)
        current_label += 1

    if not faces:
        raise ValueError("No usable face images found in dataset/. Register a user first.")

    recognizer.train(faces, np.array(labels))
    recognizer.save(MODEL_PATH)

    with open(LABELS_PATH, "wb") as f:
        pickle.dump(label_to_name, f)

    with open(VERSION_PATH, "w", encoding="utf-8") as f:
        f.write(PIPELINE_VERSION)

    return len(label_to_name), len(faces)


def load_model():
    """
    Loads the trained recognizer + label map.
    Auto-retrains once if the model was trained with an older pipeline.
    Returns (recognizer, label_to_name) or (None, None) if no model exists yet.
    """
    if not (os.path.exists(MODEL_PATH) and os.path.exists(LABELS_PATH)):
        return None, None

    try:
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            saved_version = f.read().strip()
    except OSError:
        saved_version = ""

    if saved_version != PIPELINE_VERSION and list_registered_users():
        try:
            train_model()
        except Exception:
            pass  # fall through and try loading whatever model exists

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(MODEL_PATH)

        with open(LABELS_PATH, "rb") as f:
            label_to_name = pickle.load(f)
    except (EOFError, FileNotFoundError, OSError, pickle.PickleError, ValueError):
        return None, None

    return recognizer, label_to_name
