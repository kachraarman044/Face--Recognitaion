"""
app.py
Web version of the Face Recognition Door (Flask).

Run:
    pip install -r requirements.txt
    python app.py
Then open: http://localhost:5000

The browser captures webcam frames and sends them here; the server does
face detection (Haar) + recognition (LBPH) using the same utils.py as the
desktop Tkinter app.
"""

import base64
import os
import sys
import threading
import time
from collections import Counter, deque

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import utils  # noqa: E402

app = Flask(__name__)
detector = utils.get_face_detector()

# ---------- scanner state (same voting logic as scanner.py) ----------
VOTE_WINDOW = 10
VOTE_GRANT = 6
VOTE_DENY = 8
FACE_SMALL_PX = 70
OPEN_HOLD_SECONDS = 4
DENY_COOLDOWN_SECONDS = 3

_scan_lock = threading.Lock()
_scan_votes = deque(maxlen=VOTE_WINDOW)
_scan_state = "idle"          # idle | granted | denied
_scan_state_until = 0.0
_last_conf = None
_last_granted_name = None     # shown + spoken while the door is open

# ---------- registration state ----------
_reg_lock = threading.Lock()
_reg = {"active": False, "name": None, "captured": 0, "last_capture": 0.0}

# ---------- server-side voice (pyttsx3, plays on the SERVER/PC speakers) ----------
try:
    import pyttsx3
    TTS_AVAILABLE = True
except Exception:
    pyttsx3 = None
    TTS_AVAILABLE = False

_tts_lock = threading.Lock()   # SAPI5 is not thread-safe — serialize all speech


def _speak_blocking(text):
    """Speak text on the PC speakers using pyttsx3 (fresh engine = most reliable on Windows)."""
    with _tts_lock:
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        engine.say(text)
        engine.runAndWait()
        engine.stop()

MIN_CAPTURE_INTERVAL = 0.25   # seconds between saved samples


def decode_image(payload):
    """Decode a base64 JPEG/PNG data-URL (or raw base64) into a BGR frame."""
    if not payload:
        return None
    if "," in payload:
        payload = payload.split(",", 1)[1]
    try:
        buf = np.frombuffer(base64.b64decode(payload), dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None


def face_box_list(faces, conf=None, name=None):
    boxes = []
    for (x, y, w, h) in faces:
        box = {"x": int(x), "y": int(y), "w": int(w), "h": int(h), "ok": False}
        if name is not None and conf is not None and conf <= utils.RECOGNITION_THRESHOLD:
            box["ok"] = True
        boxes.append(box)
    return boxes


# ---------------------------------------------------------------- routes

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/users")
def api_users():
    users = []
    for name in utils.list_registered_users():
        users.append({"name": name, "count": utils.user_image_count(utils.user_dataset_path(name))})
    return jsonify({"users": users, "samples_per_user": utils.IMAGES_PER_USER})


@app.route("/api/recognize", methods=["POST"])
def api_recognize():
    global _scan_state, _scan_state_until, _last_conf, _last_granted_name

    frame = decode_image((request.get_json(silent=True) or {}).get("image"))
    if frame is None:
        return jsonify({"error": "invalid image"}), 400

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = utils.detect_faces(detector, gray)
    now = time.time()

    with _scan_lock:
        if _scan_state != "idle" and now >= _scan_state_until:
            _scan_state = "idle"
            _scan_votes.clear()
            _last_granted_name = None

        if _scan_state == "idle":
            if len(faces) == 0:
                _scan_votes.clear()
                _last_conf = None
                result = {"state": "idle", "name": None, "confidence": None,
                          "message": "Point your face at the camera..."}
            else:
                (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
                face_img = utils.preprocess(gray[y:y + h, x:x + w])
                name = None
                conf = None
                if face_img is not None:
                    recognizer, label_to_name = utils.load_model()
                    if recognizer is not None:
                        label, conf = recognizer.predict(face_img)
                        _last_conf = conf
                        if conf <= utils.RECOGNITION_THRESHOLD and label in label_to_name:
                            name = label_to_name[label]

                if name is not None:
                    _scan_votes.append(name)
                elif w < FACE_SMALL_PX:
                    pass  # too far/blurry — don't vote against the user
                else:
                    _scan_votes.append(None)

                tally = Counter(_scan_votes)
                best_name, best_count = None, 0
                for nm, c in tally.items():
                    if nm is not None and c > best_count:
                        best_name, best_count = nm, c
                unknown_count = tally.get(None, 0)

                if best_name and best_count >= VOTE_GRANT:
                    _scan_state = "granted"
                    _scan_state_until = now + OPEN_HOLD_SECONDS + 1.5
                    _scan_votes.clear()
                    _last_granted_name = best_name
                    result = {"state": "granted", "name": best_name,
                              "confidence": round(float(conf or 0), 1),
                              "message": f"Welcome, {best_name}!"}
                elif unknown_count >= VOTE_DENY:
                    _scan_state = "denied"
                    _scan_state_until = now + DENY_COOLDOWN_SECONDS
                    _scan_votes.clear()
                    result = {"state": "denied", "name": None,
                              "confidence": round(float(conf), 1) if conf is not None else None,
                              "message": "Access Denied — face not registered."}
                elif best_name:
                    result = {"state": "verifying", "name": best_name,
                              "confidence": round(float(conf or 0), 1),
                              "message": f"Verifying {best_name}... ({best_count}/{VOTE_GRANT})"}
                else:
                    hint = "Move closer for a better read" if w < FACE_SMALL_PX * 1.4 else "Unknown face"
                    result = {"state": "unknown", "name": None,
                              "confidence": round(float(conf), 1) if conf is not None else None,
                              "message": hint}
        else:
            # door is held open (granted) or in deny cooldown — keep the name visible
            if _scan_state == "granted":
                result = {"state": "granted", "name": _last_granted_name,
                          "confidence": None,
                          "message": f"Welcome, {_last_granted_name}! Door is open."}
            else:
                result = {"state": "denied", "name": None, "confidence": None,
                          "message": "Access Denied — face not registered."}

    # mark the best face box as ok when recognized
    boxes = []
    for (x, y, w, h) in faces:
        ok = bool(result.get("name")) and result["state"] in ("granted", "verifying")
        boxes.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h), "ok": ok})
    result["faces"] = boxes
    result["width"] = int(frame.shape[1])
    result["height"] = int(frame.shape[0])
    return jsonify(result)


@app.route("/api/recognize/reset", methods=["POST"])
def api_recognize_reset():
    global _scan_state, _last_granted_name
    with _scan_lock:
        _scan_state = "idle"
        _scan_votes.clear()
        _last_granted_name = None
    return jsonify({"ok": True})


@app.route("/api/speak", methods=["POST"])
def api_speak():
    """Speak text on the SERVER's speakers using pyttsx3 (Python TTS)."""
    if not TTS_AVAILABLE:
        return jsonify({"error": "pyttsx3 not installed — run: pip install pyttsx3"}), 503
    text = (request.get_json(silent=True) or {}).get("text", "")[:120]
    if not text:
        return jsonify({"error": "no text"}), 400

    def _run():
        try:
            _speak_blocking(text)
        except Exception:
            pass  # never let voice crash the app

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "engine": "pyttsx3"})


@app.route("/api/voice/status")
def api_voice_status():
    return jsonify({"server_tts": TTS_AVAILABLE, "engine": "pyttsx3"})


@app.route("/api/register/start", methods=["POST"])
def api_register_start():
    data = request.get_json(silent=True) or {}
    safe_name = utils.normalize_user_name(data.get("name", ""))
    if not safe_name:
        return jsonify({"error": "Invalid name. Use letters, numbers, spaces, _ or -."}), 400
    if safe_name in utils.list_registered_users():
        return jsonify({"error": f"User '{safe_name}' already exists."}), 409

    user_dir = utils.user_dataset_path(safe_name)
    os.makedirs(user_dir, exist_ok=True)
    with _reg_lock:
        _reg.update(active=True, name=safe_name,
                    captured=utils.user_image_count(user_dir), last_capture=0.0)
    return jsonify({"ok": True, "name": safe_name,
                    "captured": _reg["captured"], "total": utils.IMAGES_PER_USER})


@app.route("/api/register/frame", methods=["POST"])
def api_register_frame():
    data = request.get_json(silent=True) or {}
    frame = decode_image(data.get("image"))
    if frame is None:
        return jsonify({"error": "invalid image"}), 400

    with _reg_lock:
        if not _reg["active"]:
            return jsonify({"error": "registration not started"}), 409
        name = _reg["name"]
        captured = _reg["captured"]

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = utils.detect_faces(detector, gray)
    img_h, img_w = gray.shape[:2]
    min_face_w = max(60, int(img_w * 0.12))

    hint = "Look straight at the camera"
    can_capture = False
    big_face = None
    if len(faces) == 0:
        hint = "No face detected — look at the camera"
    elif len(faces) > 1:
        hint = "More than one face — only you should be in frame"
    else:
        bx, by, bw, bh = max(faces, key=lambda f: f[2] * f[3])
        if bw >= min_face_w:
            big_face = (bx, by, bw, bh)
            can_capture = True
            hint = "Perfect — hold still, capturing samples..."
        else:
            hint = "Move a little closer and hold still"

    done = False
    trained = None
    if can_capture and captured < utils.IMAGES_PER_USER:
        now = time.time()
        with _reg_lock:
            if now - _reg["last_capture"] >= MIN_CAPTURE_INTERVAL and _reg["captured"] < utils.IMAGES_PER_USER:
                bx, by, bw, bh = big_face
                crop = cv2.resize(gray[by:by + bh, bx:bx + bw], utils.FACE_SIZE)
                _reg["captured"] += 1
                img_path = os.path.join(utils.user_dataset_path(name), f"img_{_reg['captured']}.jpg")
                cv2.imwrite(img_path, crop)
                _reg["last_capture"] = now
                captured = _reg["captured"]

    if captured >= utils.IMAGES_PER_USER:
        with _reg_lock:
            _reg["active"] = False
        try:
            users, images = utils.train_model()
            trained = {"users": users, "images": images}
            done = True
            hint = "Registration complete — model trained!"
        except Exception as exc:
            return jsonify({"error": f"Training failed: {exc}"}), 500

    boxes = [{"x": int(x), "y": int(y), "w": int(w), "h": int(h),
              "ok": (x, y, w, h) == big_face} for (x, y, w, h) in faces]
    return jsonify({"captured": captured, "total": utils.IMAGES_PER_USER,
                    "hint": hint, "done": done, "trained": trained,
                    "faces": boxes, "width": img_w, "height": img_h})


@app.route("/api/register/cancel", methods=["POST"])
def api_register_cancel():
    import shutil
    with _reg_lock:
        name = _reg["name"]
        _reg.update(active=False, name=None, captured=0)
    # remove partial samples from the cancelled session
    if name and name in utils.list_registered_users() and utils.user_image_count(utils.user_dataset_path(name)) < utils.IMAGES_PER_USER:
        shutil.rmtree(utils.user_dataset_path(name), ignore_errors=True)
    return jsonify({"ok": True})


@app.route("/api/delete", methods=["POST"])
def api_delete():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if name not in utils.list_registered_users():
        return jsonify({"error": f"User '{name}' not found."}), 404

    import shutil
    shutil.rmtree(utils.user_dataset_path(name), ignore_errors=True)

    remaining = utils.list_registered_users()
    if remaining:
        try:
            utils.train_model()
        except Exception as exc:
            return jsonify({"error": f"Deleted but retrain failed: {exc}"}), 500
    else:
        for path in (utils.MODEL_PATH, utils.LABELS_PATH):
            if os.path.exists(path):
                os.remove(path)

    with _scan_lock:
        _scan_state = "idle"
        _scan_votes.clear()
    return jsonify({"ok": True, "users": remaining})


if __name__ == "__main__":
    utils.ensure_dirs()
    print("\n  Face Recognition Door (Web)")
    print("  Open: http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
