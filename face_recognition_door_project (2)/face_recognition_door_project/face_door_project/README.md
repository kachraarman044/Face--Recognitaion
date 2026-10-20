# Face Recognition Door 🚪

A desktop GUI application (Python + Tkinter + OpenCV) that simulates a smart
door lock:

1. **Register** a person's face through the webcam.
2. **Scan** — point a face at the camera:
   - If the face matches a **registered** user → an animated door **opens**
     and a voice says **"Welcome, `<Name>`!"**
   - If the face is **not registered** → the door **stays closed** and it
     shows **"Access Denied"**.

See `HOW_TO_RUN.pdf` for full, step-by-step setup and run instructions.

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

Then, in the menu window:
1. Click **"Register New Face"**, type a unique name, and let it capture 5 samples.
2. Click **"Start Door Scanner"** to test recognition + the animated door.

Notes:
- Names are sanitized to letters, numbers, spaces, underscores, and hyphens.
- Duplicate names are rejected to avoid mixing face samples into the wrong account.

## Project Structure

```
face_door_project/
├── main.py                             # Entry point (menu window)
├── register.py                         # Registration window (capture + train)
├── scanner.py                          # Door scanner window (recognize + animate + speak)
├── door_animation.py                   # Animated double-door widget (Tkinter Canvas)
├── utils.py                            # Paths, dataset helpers, LBPH training/loading
├── haarcascade_frontalface_default.xml # OpenCV face-detector model
├── requirements.txt
├── dataset/                            # Captured face images, one folder per user
└── trainer/                            # Trained model (trainer.yml + labels.pickle)
```

## How Recognition Works

- Face **detection** uses OpenCV's Haar Cascade (`haarcascade_frontalface_default.xml`).
- Face **recognition** uses OpenCV's built-in **LBPH** (Local Binary Patterns
  Histograms) recognizer — no external face-recognition/dlib install needed.
- The door only opens after several consecutive matching frames in a row
  (to avoid flicker), and access is denied only after several consecutive
  unrecognized frames.
- You can tune strictness via `RECOGNITION_THRESHOLD` in `utils.py`
  (lower = stricter).

## Notes & Limitations

- This is an educational/demo project, **not** a production security
  system. LBPH recognition can be fooled by a photo/video of a registered
  user, poor lighting, etc.
- Requires a working webcam and a graphical desktop (Tkinter needs a display).
- Voice output uses `pyttsx3` (fully offline, no internet needed).
