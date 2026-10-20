"""
register.py
Registration window: captures face samples for a new user from the webcam,
saves them to dataset/<name>/, then (re)trains the recognizer.
"""

import os
import time
import tkinter as tk
from tkinter import messagebox

import cv2
from PIL import Image, ImageTk

import utils
import theme


class RegisterWindow(tk.Toplevel):
    def __init__(self, master, on_done=None):
        super().__init__(master)
        self.title("Register New Face")
        self.configure(bg=theme.BG)
        self.resizable(True, True)
        self.minsize(540, 640)
        self.on_done = on_done

        self.cap = None
        self.detector = utils.get_face_detector()
        self.running = False
        self.captured = 0
        self.user_name = None
        self.last_capture_time = 0
        self.cam_fail_count = 0  # consecutive camera read failures
        self._flash_until = 0

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI ----------

    def _build_ui(self):
        pad = 16

        tk.Label(
            self, text="Register New Face", bg=theme.BG, fg=theme.TEXT,
            font=theme.FONT_TITLE
        ).pack(pady=(pad + 4, 2))

        tk.Label(
            self, text="Enter a name, then hold your face steady in the frame.",
            bg=theme.BG, fg=theme.TEXT_MUTED, font=theme.FONT_SUBTITLE
        ).pack(pady=(0, 10))

        # ---------- name input card ----------
        card = theme.make_card(self)
        card.pack(fill="x", padx=pad, pady=(0, 10))

        tk.Label(card, text="USER NAME", bg=theme.BG_CARD, fg=theme.ACCENT,
                 font=("Consolas", 9, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        self.name_entry = theme.make_entry(card, width=24)
        self.name_entry.pack(fill="x", padx=14, pady=(0, 12))

        # ---------- video feed (scales with window) ----------
        self.video_wrap = tk.Frame(self, bg=theme.BORDER, highlightthickness=0)
        self.video_wrap.pack(fill="x", padx=pad, pady=4)
        self.video_label = tk.Label(self.video_wrap, bg="black")
        self.video_label.pack(fill="x", padx=2, pady=2)
        self._video_target_w = 560
        self.bind("<Configure>", self._on_resize, add="+")

        # ---------- progress ring + label ----------
        prog_row = tk.Frame(self, bg=theme.BG)
        prog_row.pack(fill="x", padx=pad, pady=(10, 2))

        self.ring = theme.RingProgress(prog_row, size=96, color=theme.ACCENT)
        self.ring.canvas.pack(side="left", padx=(0, 14))

        info = tk.Frame(prog_row, bg=theme.BG)
        info.pack(side="left", fill="x", expand=True)

        self.progress_label = tk.Label(
            info, text=f"0 / {utils.IMAGES_PER_USER} samples captured",
            bg=theme.BG, fg=theme.ACCENT, font=theme.FONT_BOLD, anchor="w"
        )
        self.progress_label.pack(anchor="w")

        self.hint_label = tk.Label(
            info, text="Press Start Capture to begin",
            bg=theme.BG, fg=theme.TEXT_MUTED, font=theme.FONT_SMALL, anchor="w"
        )
        self.hint_label.pack(anchor="w", pady=(4, 0))

        # ---------- buttons ----------
        btn_frame = tk.Frame(self, bg=theme.BG)
        btn_frame.pack(pady=(12, pad))

        self.start_btn = theme.make_button(
            btn_frame, text="Start Capture", command=self.start_capture,
            accent=theme.ACCENT, width=14
        )
        self.start_btn.pack(side="left", padx=6)

        self.cancel_btn = theme.make_button(
            btn_frame, text="Close", command=self._on_close,
            accent="#475569", width=10
        )
        self.cancel_btn.pack(side="left", padx=6)

    def _set_video_border(self, color):
        self.video_wrap.configure(bg=color)

    def _on_resize(self, event=None):
        if event is None or event.widget is not self:
            return
        try:
            avail = self.winfo_width()
        except tk.TclError:
            return
        if avail > 100:
            self._video_target_w = avail - 2 * 16 - 4

    # ---------- capture logic ----------

    def start_capture(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Please enter a name before capturing.", parent=self)
            return

        safe_name = utils.normalize_user_name(name)
        if not safe_name:
            messagebox.showwarning("Invalid name", "Please use a valid name (letters/numbers).", parent=self)
            return

        if safe_name in utils.list_registered_users():
            messagebox.showwarning(
                "User already exists",
                f"A user named '{safe_name}' already exists. Please choose a different name.",
                parent=self,
            )
            return

        self.user_name = safe_name
        self.user_dir = utils.user_dataset_path(self.user_name)
        os.makedirs(self.user_dir, exist_ok=True)
        self.captured = utils.user_image_count(self.user_dir)
        self.ring.set(self.captured / utils.IMAGES_PER_USER)
        self.progress_label.config(
            text=f"{self.captured} / {utils.IMAGES_PER_USER} samples captured"
        )
        self.hint_label.config(text="Scanning... keep your face in the frame", fg=theme.WARNING)
        self._set_video_border(theme.WARNING)

        self.name_entry.config(state="disabled")
        self.start_btn.config(state="disabled")

        self.cap = utils.open_camera(0)
        if not self.cap.isOpened():
            messagebox.showerror("Camera error", "Could not open the webcam.", parent=self)
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
                    "Webcam stopped responding. Please check the connection.",
                    parent=self,
                )
                self._on_close()
                return
            self.after(30, self._update_frame)
            return
        self.cam_fail_count = 0

        frame = cv2.flip(frame, 1)

        # Detect on the FULL-RESOLUTION frame so we capture sharp, detailed
        # crops even when the face is a little farther from the camera.
        gray_full = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = utils.detect_faces(self.detector, gray_full)

        # A sample is only good if the face is large enough and clearly sharp.
        big_face = None
        if len(faces) > 0:
            bx, by, bw, bh = max(faces, key=lambda f: f[2] * f[3])
            if len(faces) == 1 and bw >= utils.MIN_FACE_PX:
                big_face = (bx, by, bw, bh)

        # ---------- display downscale (map boxes) ----------
        target_w = self._video_target_w
        disp_frame = frame
        disp_faces = faces
        if target_w > 50 and abs(frame.shape[1] - target_w) > 8:
            scale = target_w / frame.shape[1]
            disp_frame = cv2.resize(
                frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)),
                interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
            )
            disp_faces = [
                (int(x * scale), int(y * scale), int(w * scale), int(h * scale), ok_face)
                for (x, y, w, h, ok_face) in self._tag_faces(faces, big_face)
            ]
        else:
            disp_faces = self._tag_faces(faces, big_face)

        for (x, y, w, h, ok_face) in disp_faces:
            box_color = (34, 211, 238) if ok_face else (239, 68, 68)
            cv2.rectangle(disp_frame, (x, y), (x + w, y + h), box_color, 1)
            for (cx, cy, dx, dy) in (
                (x, y, 1, 1), (x + w, y, -1, 1),
                (x, y + h, 1, -1), (x + w, y + h, -1, -1),
            ):
                cv2.line(disp_frame, (cx, cy), (cx + 28 * dx, cy), (34, 211, 238), 3)
                cv2.line(disp_frame, (cx, cy), (cx, cy + 28 * dy), (34, 211, 238), 3)
            tag = "CAPTURING" if ok_face else "MOVE CLOSER"
            cv2.putText(disp_frame, tag, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, box_color, 2)

        # Capture a sample every ~200ms while exactly one large face is visible.
        now = time.time()
        if (
            big_face is not None
            and self.captured < utils.IMAGES_PER_USER
            and now - self.last_capture_time > 0.2
        ):
            bx, by, bw, bh = big_face
            face_img = gray_full[by:by + bh, bx:bx + bw]
            face_img = cv2.resize(face_img, utils.FACE_SIZE)
            self.captured += 1
            img_path = os.path.join(self.user_dir, f"img_{self.captured}.jpg")
            cv2.imwrite(img_path, face_img)
            self.last_capture_time = now
            self._flash_until = now + 0.12
            self.progress_label.config(
                text=f"{self.captured} / {utils.IMAGES_PER_USER} samples captured"
            )
            self.ring.set(self.captured / utils.IMAGES_PER_USER)

        # live guidance + neon flash on capture
        if now < self._flash_until:
            self._set_video_border("#ffffff")
        elif len(faces) == 0:
            self._set_video_border(theme.WARNING)
            self.hint_label.config(text="No face detected — look straight at the camera",
                                   fg=theme.WARNING)
        elif len(faces) > 1:
            self._set_video_border(theme.DANGER)
            self.hint_label.config(text="More than one face — only you should be in frame",
                                   fg=theme.DANGER)
        elif big_face is None:
            self._set_video_border(theme.WARNING)
            self.hint_label.config(text="Move a little closer and hold still",
                                   fg=theme.WARNING)
        else:
            self._set_video_border(theme.ACCENT)
            self.hint_label.config(text="Perfect — hold still, capturing samples...",
                                   fg=theme.ACCENT)

        # Show live preview
        rgb = cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.imgtk = imgtk
        self.video_label.configure(image=imgtk)

        if self.captured >= utils.IMAGES_PER_USER:
            self._finish_capture()
            return

        self.after(30, self._update_frame)

    @staticmethod
    def _tag_faces(faces, big_face):
        """Return [(x, y, w, h, ok)] with the good capture face flagged True."""
        tagged = []
        for (x, y, w, h) in faces:
            ok_face = big_face is not None and (x, y, w, h) == big_face
            tagged.append((x, y, w, h, ok_face))
        return tagged

    def _finish_capture(self):
        self.running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        self._set_video_border(theme.SUCCESS)
        self.hint_label.config(text="Training model...", fg=theme.SUCCESS)

        try:
            num_users, num_images = utils.train_model()
            messagebox.showinfo(
                "Registration complete",
                f"'{self.user_name}' registered successfully!\n\n"
                f"Model trained on {num_users} user(s), {num_images} image(s) total."
            )
        except Exception as exc:
            messagebox.showerror("Training failed", str(exc), parent=self)

        if self.on_done:
            self.on_done()
        self.destroy()

    def _on_close(self):
        self.running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.destroy()
