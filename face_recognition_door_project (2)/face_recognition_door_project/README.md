# 🚪 Face Recognition Door — Smart Lock System

A desktop GUI application built with **Python, OpenCV, and Tkinter** that simulates a
smart door lock using face recognition.

- **Register** a person's face through the webcam (5 samples → auto-trains the model).
- **Scan** — point a face at the camera:
  - Registered face → animated door **opens** + voice says **"Welcome, `<Name>`!"**
  - Unknown face → door **stays closed** + **"Access Denied"**
- **Delete** a registered user (removes their face data and retrains the model).

> ⚠️ Educational/demo project — **not** a production security system.

---

## 📋 Requirements

| Item | Version |
|------|---------|
| Python | 3.9 – 3.11 (64-bit) |
| OS | Windows / Linux / macOS |
| Extras | A working **webcam** and a **graphical desktop** (Tkinter) |

Python packages (see `face_door_project/requirements.txt`):

```
opencv-contrib-python==4.10.0.84
numpy==1.26.4
pillow==10.4.0
pyttsx3==2.90
```

---

## ⚡ Quick Start

### Option A — Web version (🌐 runs in the browser — recommended for online use)

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>

python -m venv venv
venv\Scripts\activate          # Windows:  source venv/bin/activate (Linux/macOS)

pip install -r face_door_project/requirements.txt
python face_door_project/app.py
```

Open **http://localhost:5000** → camera, face scan, register, delete — everything in the browser.

### Option B — Desktop version (Tkinter GUI)

```bash
python face_door_project/main.py
```

### Using the app

1. **Register New Face** — enter a unique name, look at the camera while it captures 5 samples, the model trains automatically.
2. **Start Door Scanner** — live recognition + animated double door + voice output.
3. **Delete Registered User** — permanently remove a face and retrain.

**Tips**
- Names allow letters, numbers, spaces, `_` and `-` only; duplicate names are rejected.
- The door opens only after several **consecutive** matching frames (anti-flicker).
- Tune strictness via `RECOGNITION_THRESHOLD` in `face_door_project/utils.py` (lower = stricter).

---

## 🧠 How It Works

```
Webcam frame
   │
   ▼
Haar Cascade (haarcascade_frontalface_default.xml)  →  face detection
   │
   ▼
CLAHE preprocessing (pipeline: "2-clahe")
   │
   ▼
LBPH recognizer (OpenCV, trained on dataset/)       →  face recognition
   │
   ├── match + confidence OK  →  N consecutive frames  →  door OPEN  +  pyttsx3 voice
   └── no match               →  N consecutive frames  →  Access Denied
```

- **Detection:** OpenCV Haar Cascade — no dlib / no external model downloads.
- **Recognition:** OpenCV **LBPH** (Local Binary Patterns Histograms).
- **Voice:** `pyttsx3` (fully offline TTS).

---

## 📁 Project Structure

```
.
├── README.md                                # You are here
├── Face_Recognition_Door_Project_Report.pdf # Project report
└── face_door_project/
    ├── app.py                               # 🌐 Flask web version (browser camera)
    ├── templates/index.html                 # Web UI: camera + door animation
    ├── main.py                              # Desktop entry point (menu window)
    ├── register.py                          # Registration window (capture + train)
    ├── scanner.py                           # Scanner window (recognize + animate + speak)
    ├── door_animation.py                    # Animated double-door widget (Tkinter Canvas)
    ├── theme.py                             # Neon dark theme, buttons, animations
    ├── utils.py                             # Paths, dataset helpers, LBPH training/loading
    ├── haarcascade_frontalface_default.xml  # OpenCV face-detector model
    ├── requirements.txt
    ├── README.md                            # Detailed module-level docs
    ├── dataset/                             # Captured face images (one folder per user) — created at runtime
    └── trainer/                             # trainer.yml + labels.pickle — created at runtime
```

> `dataset/` and `trainer/` are generated automatically when you register faces, so a
> fresh clone starts clean.

---

## 🔧 Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: cv2` | `pip install -r face_door_project/requirements.txt` (must be `opencv-contrib-python`) |
| `TclError: no display name` | Run on a machine with a GUI (not a headless server); on Linux install `python3-tk` |
| Webcam not opening | Close other apps using the camera; check OS camera permissions |
| `pyttsx3` error on Linux | `sudo apt install espeak` |
| Faces not recognized | Improve lighting, re-register samples, or lower `RECOGNITION_THRESHOLD` in `utils.py` |
| `python` not found | Use `py -3` on Windows, or install 64-bit Python 3.11 |

---

## 🌐 Running it LIVE (online)

The **web version** (`app.py`) runs in any browser — it can be deployed online.

### Free deploy — Render.com (5 min)

1. Push this repo to GitHub.
2. Go to [render.com](https://render.com) → **New → Web Service** → connect your repo.
3. Settings:
   - **Root Directory:** `face_door_project`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py`
4. Deploy → you get an `https://...onrender.com` link.
5. Open that link on your phone/PC → allow camera → register + scan.

> Browser camera works only on **HTTPS** pages (Render provides HTTPS automatically).

### Local test

```bash
python face_door_project/app.py
# open http://localhost:5000
```

### How it works

```
Browser (getUserMedia webcam frame, every ~300ms)
        │  base64 JPEG POST
        ▼
Flask /api/recognize  →  Haar detect + LBPH predict (same utils.py)
        │  JSON { state, name, faces }
        ▼
Browser: draws face boxes + opens/shakes the CSS door + speaks (speechSynthesis)
```

Notes:
- Face **data stays on the server** — only compressed JPEG frames travel between browser and server.
- Desktop Tkinter version still works the same: `python face_door_project/main.py`.
- `pyttsx3` is optional for the web version (browser's own voice is used).

---

## 📄 License

Free to use for learning and demo purposes.
