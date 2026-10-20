"""
door_animation.py
A small animated "double door" drawn on a Tkinter Canvas.

The door is made of two panels that slide apart (open) or slide
back together (close) over a series of animation steps.
"""

import tkinter as tk

import theme


class DoorAnimation:
    STATE_CLOSED = "closed"
    STATE_OPENING = "opening"
    STATE_OPEN = "open"
    STATE_CLOSING = "closing"

    def __init__(self, canvas: tk.Canvas, x, y, width, height, steps=18):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.steps = steps          # how many animation frames a full open/close takes
        self.progress = 0           # 0 = fully closed, steps = fully open
        self.state = self.STATE_CLOSED

        self.frame_id = None
        self.left_panel = None
        self.right_panel = None
        self.left_handle = None
        self.right_handle = None
        self.status_text = None

        self._draw_floor()
        self._draw_frame()
        self._draw_panels()
        self.status_text = self.canvas.create_text(
            self.x + self.width / 2,
            self.y + self.height + 34,
            text="Scanning...",
            font=("Segoe UI", 14, "bold"),
            fill="#94a3b8",
        )

    # ---------- drawing ----------

    def _draw_floor(self):
        # subtle floor line under the door
        self.canvas.create_line(
            self.x - 24, self.y + self.height + 12,
            self.x + self.width + 24, self.y + self.height + 12,
            fill=theme.BORDER, width=2,
        )

    def _draw_frame(self):
        pad = 12
        # outer neon glow frame (dim, wide)
        self.canvas.create_rectangle(
            self.x - pad, self.y - pad,
            self.x + self.width + pad, self.y + self.height + pad,
            outline=theme.ACCENT_DIM, width=1, fill=""
        )
        # outer wall/frame
        self.canvas.create_rectangle(
            self.x - pad + 3, self.y - pad + 3,
            self.x + self.width + pad - 3, self.y + self.height + pad - 3,
            outline="#16233c", width=10, fill="#0a1222",
        )
        # inner accent trim
        self.canvas.create_rectangle(
            self.x - 2, self.y - 2,
            self.x + self.width + 2, self.y + self.height + 2,
            outline=theme.ACCENT, width=1, fill="",
        )

    def _draw_panels(self):
        half = self.width / 2
        # Left panel
        self.left_panel = self.canvas.create_rectangle(
            self.x, self.y,
            self.x + half, self.y + self.height,
            fill="#12223c", outline=theme.ACCENT_DIM, width=1,
        )
        self.left_handle = self.canvas.create_oval(
            self.x + half - 18, self.y + self.height / 2 - 5,
            self.x + half - 8, self.y + self.height / 2 + 5,
            fill=theme.ACCENT, outline="",
        )
        # Right panel
        self.right_panel = self.canvas.create_rectangle(
            self.x + half, self.y,
            self.x + self.width, self.y + self.height,
            fill="#12223c", outline=theme.ACCENT_DIM, width=1,
        )
        self.right_handle = self.canvas.create_oval(
            self.x + half + 8, self.y + self.height / 2 - 5,
            self.x + half + 18, self.y + self.height / 2 + 5,
            fill=theme.ACCENT, outline="",
        )
        # decorative panel lines (tech look)
        for offset in (30, 90, 150, 210):
            if offset < self.height:
                self.canvas.create_line(
                    self.x + 14, self.y + offset,
                    self.x + half - 14, self.y + offset,
                    fill="#1c3358", width=1,
                )
                self.canvas.create_line(
                    self.x + half + 14, self.y + offset,
                    self.x + self.width - 14, self.y + offset,
                    fill="#1c3358", width=1,
                )
        # center seam glow
        self.canvas.create_line(
            self.x + half, self.y + 4,
            self.x + half, self.y + self.height - 4,
            fill=theme.ACCENT, width=1,
        )

    def _apply_progress(self):
        """Move the two panels apart based on self.progress (0..steps)."""
        half = self.width / 2
        max_slide = half * 0.92  # panels slide almost fully into the frame walls
        slide = (self.progress / self.steps) * max_slide

        # Left panel moves left, right panel moves right
        self.canvas.coords(
            self.left_panel,
            self.x - slide, self.y,
            self.x + half - slide, self.y + self.height,
        )
        self.canvas.coords(
            self.left_handle,
            self.x + half - slide - 18, self.y + self.height / 2 - 5,
            self.x + half - slide - 8, self.y + self.height / 2 + 5,
        )
        self.canvas.coords(
            self.right_panel,
            self.x + half + slide, self.y,
            self.x + self.width + slide, self.y + self.height,
        )
        self.canvas.coords(
            self.right_handle,
            self.x + half + slide + 8, self.y + self.height / 2 - 5,
            self.x + half + slide + 18, self.y + self.height / 2 + 5,
        )

    # ---------- animation control ----------

    def set_status(self, text, color="#cfd8dc"):
        self.canvas.itemconfig(self.status_text, text=text, fill=color)

    def open_door(self, on_complete=None):
        if self.state in (self.STATE_OPEN, self.STATE_OPENING):
            return
        self.state = self.STATE_OPENING
        self._animate_step(direction=1, on_complete=on_complete)

    def close_door(self, on_complete=None):
        if self.state in (self.STATE_CLOSED, self.STATE_CLOSING):
            return
        self.state = self.STATE_CLOSING
        self._animate_step(direction=-1, on_complete=on_complete)

    def _animate_step(self, direction, on_complete=None):
        self.progress += direction
        self.progress = max(0, min(self.steps, self.progress))
        self._apply_progress()

        finished = (direction == 1 and self.progress >= self.steps) or \
                   (direction == -1 and self.progress <= 0)

        if finished:
            self.state = self.STATE_OPEN if direction == 1 else self.STATE_CLOSED
            if on_complete:
                on_complete()
            return

        self.frame_id = self.canvas.after(
            25, lambda: self._animate_step(direction, on_complete)
        )

    def cancel(self):
        if self.frame_id is not None:
            try:
                self.canvas.after_cancel(self.frame_id)
            except Exception:
                pass
            self.frame_id = None
