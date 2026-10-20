"""
scanner.py
The main "door scanner" window.

- Shows a live webcam feed with a HUD-style scanning overlay.
- Detects faces and runs them through the trained LBPH recognizer.
- If the face belongs to a REGISTERED user -> animated door opens
  and a voice says "Welcome, <Name>!".
- If the face is NOT recognized -> door stays shut and it shows
  "Access Denied".
"""

import threading
import time
import tkinter as tk
from collections import Counter, deque
from tkinter import messagebox

import cv2
from PIL import Image, ImageTk

import utils
import theme
from door_animation import DoorAnimation

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

# Rolling-window voting: look at the last VOTE_WINDOW frames instead of a
# fragile consecutive streak. A single missed frame no longer resets progress.
VOTE_WINDOW = 10
VOTE_GRANT = 6    # same registered name in >=6 of the last 10 frames -> open
VOTE_DENY = 8     # unknown face in >=8 of the last 10 frames -> deny
# Faces narrower than this (at 720p) are "too far/blurry" for a fair verdict.
FACE_SMALL_PX = 70
# Seconds the door stays open once granted, before it auto-closes.
OPEN_HOLD_SECONDS = 4
# Seconds to wait before allowing a new scan after a denied attempt.
DENY_COOLDOWN_SECONDS = 3

NEON_CYAN = (34, 211, 238)
NEON_GREEN = (34, 197, 94)
NEON_RED = (239, 68, 68)


def speak_async(text):
    """Speak text on a background thread so the GUI never freezes."""
    if not TTS_AVAILABLE:
        return

    def _run():
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 165)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


class ScannerWindow(tk.Toplevel):
    STATE_IDLE = "idle"
    STATE_GRANTED = "granted"
    STATE_DENIED = "denied"

    def __init__(self, master):
        super().__init__(master)
        self.title("Face Recognition Door")
        self.configure(bg=theme.BG)
        self.resizable(True, True)
        self.minsize(760, 560)

        self.detector = utils.get_face_detector()
        self.recognizer, self.label_to_name = utils.load_model()
        if self.recognizer is None:
            messagebox.showwarning(
                "No trained model",
                "No registered faces found yet.\nPlease register at least one user first.",
                parent=master,
            )
            self.destroy()
            return

        self.cap = None
        self.running = False
        self.cam_fail_count = 0  # consecutive camera read failures

        self._votes = deque(maxlen=VOTE_WINDOW)  # rolling name/None votes
        self._last_conf = None
        self.state = self.STATE_IDLE
        self.state_until = 0  # timestamp after which we can return to idle
        self._sweep_y = 0        # HUD scanner sweep line
        self._tick = 0           # pulse animation tick

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_camera()
        self._pulse()

    # ---------- UI ----------

    def _build_ui(self):
        pad = 16

        tk.Label(
            self, text="Smart Door — Face Scanner", bg=theme.BG, fg=theme.TEXT,
            font=theme.FONT_TITLE
        ).pack(pady=(pad, 2))
        tk.Label(
            self, text="Registered faces unlock the door. Unknown faces are denied.",
            bg=theme.BG, fg=theme.TEXT_MUTED, font=theme.FONT_SUBTITLE
        ).pack(pady=(0, 10))

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=pad, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # webcam feed inside a glowing border card (scales with window)
        self.video_wrap = tk.Frame(body, bg=theme.BORDER)
        self.video_wrap.grid(row=0, column=0, padx=(0, pad), sticky="nsew")
        self.video_label = tk.Label(self.video_wrap, bg="black")
        self.video_label.pack(fill="both", expand=True, padx=2, pady=2)
        self._video_target_w = 640

        # door panel card
        door_card = theme.make_card(body)
        door_card.grid(row=0, column=1, sticky="n")
        self.canvas = tk.Canvas(
            door_card, width=260, height=340,
            bg=theme.BG_CARD, highlightthickness=0
        )
        self.canvas.pack(padx=10, pady=10)
        self.door = DoorAnimation(self.canvas, x=40, y=20, width=180, height=260)

        # ---------- status pill ----------
        pill_wrap = tk.Frame(self, bg=theme.BG)
        pill_wrap.pack(pady=(4, 6))
        self.status_pill = tk.Label(
            pill_wrap, text="●  SCANNING", bg=theme.BG_INPUT, fg=theme.TEXT_MUTED,
            font=("Consolas", 10, "bold"), padx=16, pady=4,
            highlightbackground=theme.BORDER, highlightthickness=1
        )
        self.status_pill.pack()

        self.info_label = tk.Label(
            self, text="Point your face at the camera...",
            bg=theme.BG, fg=theme.TEXT_MUTED, font=theme.FONT_BODY
        )
        self.info_label.pack(pady=(0, pad))

        theme.make_button(
            self, text="Close Scanner", command=self._on_close,
            accent="#475569", width=16
        ).pack(pady=(0, pad))

        # responsive: video scales to the available column width
        self.bind("<Configure>", self._on_resize, add="+")

    def _on_resize(self, event=None):
        if event is None or event.widget is not self:
            return
        try:
            avail = self.video_wrap.winfo_width()
        except tk.TclError:
            return
        if avail > 50:
            self._video_target_w = avail - 4

    def _set_pill(self, text, color):
        self.status_pill.config(text=f"●  {text}", fg=color,
                                highlightbackground=color)

    def _set_border(self, color):
        self.video_wrap.configure(bg=color)

    def _pulse(self):
        """Soft pulsing glow on the video border while scanning."""
        if not self.running:
            return
        try:
            if self.state == self.STATE_IDLE:
                # alternate between dim and bright accent
                self._tick += 1
                phase = (self._tick // 12) % 2
                self._set_border(theme.ACCENT if phase else theme.ACCENT_DIM)
        except tk.TclError:
            return
        self.after(90, self._pulse)

    # ---------- camera / recognition loop ----------

    def _start_camera(self):
        self.cap = utils.open_camera(0)
        if not self.cap.isOpened():
            messagebox.showerror("Camera error", "Could not open the webcam.")
            self._on_close()
            return
        self.running = True
        self._update_frame()

    def _update_frame(self):
        if not self.running:
            return

        ok, frame = self.cap.read()
        if not ok:
            self.cam_fail_count += 1
            if self.cam_fail_count >= 30:
                self.running = False
                messagebox.showerror(
                    "Camera lost",
                    "Webcam stopped responding. Please check the connection and reopen the scanner.",
                    parent=self,
                )
                self._on_close()
                return
            self.after(30, self._update_frame)
            return
        self.cam_fail_count = 0

        frame = cv2.flip(frame, 1)

        # Detect + recognize on the FULL-RESOLUTION frame (720p), so faces
        # that are farther from the camera still have enough pixels to match.
        gray_full = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = utils.detect_faces(self.detector, gray_full)

        now = time.time()

        # If we're in a "granted" or "denied" cool-down, just keep showing
        # the frame and wait for the timer to expire.
        if self.state != self.STATE_IDLE:
            if now >= self.state_until:
                self._reset_to_idle()
        else:
            self._process_faces(gray_full, faces)

        # ---------- display downscale (after processing, boxes mapped) ----------
        disp_frame = frame
        disp_faces = faces
        target_w = self._video_target_w
        if target_w > 50 and abs(frame.shape[1] - target_w) > 8:
            scale = target_w / frame.shape[1]
            disp_frame = cv2.resize(
                frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)),
                interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
            )
            disp_faces = [
                (int(x * scale), int(y * scale), int(fw * scale), int(fh * scale))
                for (x, y, fw, fh) in faces
            ]

        # ---------- HUD overlay ----------
        self._draw_hud(disp_frame, disp_faces)

        rgb = cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.imgtk = imgtk
        self.video_label.configure(image=imgtk)

        self.after(30, self._update_frame)

    def _draw_hud(self, frame, faces):
        h, w = frame.shape[:2]

        # pick theme color by state
        if self.state == self.STATE_GRANTED:
            color = NEON_GREEN
        elif self.state == self.STATE_DENIED:
            color = NEON_RED
        else:
            color = NEON_CYAN

        # corner brackets (full frame)
        m, ln = 12, 34
        for (cx, cy, dx, dy) in (
            (m, m, 1, 1), (w - m, m, -1, 1),
            (m, h - m, 1, -1), (w - m, h - m, -1, -1),
        ):
            cv2.line(frame, (cx, cy), (cx + ln * dx, cy), color, 2)
            cv2.line(frame, (cx, cy), (cx, cy + ln * dy), color, 2)

        # sweeping scan line
        if self.state == self.STATE_IDLE:
            self._sweep_y = (self._sweep_y + 5) % h
            sy = self._sweep_y
            cv2.line(frame, (m, sy), (w - m, sy), color, 1)
            # small gradient trail
            for i in range(1, 10):
                shade = int(40 * (1 - i / 10))
                cv2.line(frame, (m, sy - i), (w - m, sy - i), (shade // 3, shade, shade), 1)

        # face boxes with name/confidence-free tag
        for (x, y, fw, fh) in faces:
            cv2.rectangle(frame, (x, y), (x + fw, y + fh), color, 1)
            for (cx, cy, dx, dy) in (
                (x, y, 1, 1), (x + fw, y, -1, 1),
                (x, y + fh, 1, -1), (x + fw, y + fh, -1, -1),
            ):
                cv2.line(frame, (cx, cy), (cx + 22 * dx, cy), color, 3)
                cv2.line(frame, (cx, cy), (cx, cy + 22 * dy), color, 3)

        # top-left HUD text
        cv2.putText(frame, "FACE SCAN", (16, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
        # top-right frame counter style text
        status_txt = {"idle": "SCANNING", "granted": "ACCESS GRANTED",
                      "denied": "ACCESS DENIED"}[self.state]
        cv2.putText(frame, status_txt, (w - 16 - 9 * len(status_txt), 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)

        # bottom status bar
        cv2.rectangle(frame, (0, h - 26), (w, h), (10, 16, 32), -1)
        cv2.putText(frame, f"FACES: {len(faces)}", (16, h - 9),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

        # mid-bottom hint: distance guidance or live match distance
        hint = ""
        if len(faces) > 0:
            (_, _, fw, _) = max(faces, key=lambda f: f[2] * f[3])
            if fw < FACE_SMALL_PX:
                hint = "MOVE CLOSER FOR A BETTER READ"
                hint_color = NEON_RED
            elif self._last_conf is not None:
                hint = f"MATCH DIST: {self._last_conf:.0f}  (lower = better)"
                hint_color = color
            else:
                hint_color = color
        else:
            hint_color = color
        if hint:
            cv2.putText(frame, hint, (16 + 10 * len("FACES: 0"), h - 9),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, hint_color, 1, cv2.LINE_AA)

        conf_txt = f"MODE: {status_txt}"
        cv2.putText(frame, conf_txt, (w - 16 - 7 * len(conf_txt), h - 9),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    def _process_faces(self, gray_full, faces):
        if len(faces) == 0:
            self._votes.clear()
            self._last_conf = None
            self.door.set_status("Scanning...", "#94a3b8")
            self._set_pill("SCANNING", theme.TEXT_MUTED)
            self.info_label.config(text="Point your face at the camera...")
            return

        # Use the largest detected face
        (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
        face_img = utils.preprocess(gray_full[y:y + h, x:x + w])
        if face_img is None:
            return

        label, confidence = self.recognizer.predict(face_img)
        self._last_conf = confidence

        # confidence is a distance: LOWER = better match
        if confidence <= utils.RECOGNITION_THRESHOLD and label in self.label_to_name:
            name = self.label_to_name[label]   # exact registered name
            self._votes.append(name)
        elif w < FACE_SMALL_PX:
            # Too far/blurry for a fair verdict — don't vote against the user.
            pass
        else:
            self._votes.append(None)

        tally = Counter(self._votes)
        best_name, best_count = None, 0
        for nm, count in tally.items():
            if nm is not None and count > best_count:
                best_name, best_count = nm, count
        unknown_count = tally.get(None, 0)

        if best_name and best_count >= VOTE_GRANT:
            self._grant_access(best_name)
        elif unknown_count >= VOTE_DENY:
            self._deny_access()
        elif best_name:
            self.door.set_status(f"Verifying {best_name}...", theme.WARNING)
            self._set_pill("VERIFYING", theme.WARNING)
            self._set_border(theme.WARNING)
            self.info_label.config(
                text=f"Recognizing {best_name}... ({best_count}/{VOTE_GRANT})"
            )
        else:
            self.door.set_status("Unknown face", theme.DANGER)
            self._set_pill("UNKNOWN FACE", theme.DANGER)
            self.info_label.config(text="Face not recognized. Access will be denied.")

    def _grant_access(self, name):
        self._votes.clear()
        self.state = self.STATE_GRANTED
        self.state_until = time.time() + OPEN_HOLD_SECONDS + 1.5  # extra buffer for close anim

        # name is always the exact registered name from label_to_name
        self.door.set_status(f"Welcome, {name}!", theme.SUCCESS)
        self._set_pill("ACCESS GRANTED", theme.SUCCESS)
        self._set_border(theme.SUCCESS)
        self.info_label.config(text=f"✅ Access Granted - Welcome, {name}!")
        speak_async(f"Welcome, {name}!")

        def after_open():
            self.after(int(OPEN_HOLD_SECONDS * 1000), lambda: self.door.close_door())

        self.door.open_door(on_complete=after_open)

    def _deny_access(self):
        self._votes.clear()
        self.state = self.STATE_DENIED
        self.state_until = time.time() + DENY_COOLDOWN_SECONDS

        self.door.set_status("Access Denied", theme.DANGER)
        self._set_pill("ACCESS DENIED", theme.DANGER)
        self._set_border(theme.DANGER)
        self.info_label.config(text="❌ Access Denied - face not registered.")
        speak_async("Access denied.")
        # Door never opens for an unregistered face.

    def _reset_to_idle(self):
        self.state = self.STATE_IDLE
        self._votes.clear()
        self._last_conf = None
        self.door.set_status("Scanning...", "#94a3b8")
        self._set_pill("SCANNING", theme.TEXT_MUTED)
        self.info_label.config(text="Point your face at the camera...")

    def _on_close(self):
        self.running = False
        self.door.cancel()
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.destroy()
