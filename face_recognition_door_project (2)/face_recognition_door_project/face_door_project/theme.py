"""
theme.py
Shared dark-neon theme, fonts, animated background and fancy canvas widgets.
Only UI styling lives here - no business logic.
"""

import math
import random
import tkinter as tk

# ---------- palette ----------
BG = "#04091a"
BG_CARD = "#0c1428"
BG_INPUT = "#101b35"
ACCENT = "#22d3ee"
ACCENT_DIM = "#0e7490"
SUCCESS = "#22c55e"
DANGER = "#ef4444"
WARNING = "#f59e0b"
TEXT = "#f1f5f9"
TEXT_MUTED = "#7d93b5"
BORDER = "#1c2b4a"

# ---------- fonts ----------
FONT_TITLE = ("Segoe UI", 17, "bold")
FONT_SUBTITLE = ("Segoe UI", 10)
FONT_BODY = ("Segoe UI", 11)
FONT_BOLD = ("Segoe UI", 11, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_BUTTON = ("Segoe UI", 12, "bold")


# ================= widgets =================

def style_button(btn, accent=ACCENT, hover=None):
    hover = hover or _lighten(accent, 0.2)
    btn.configure(
        bg=accent, fg="#041018",
        activebackground=hover, activeforeground="#041018",
        font=FONT_BUTTON, relief="flat", bd=0, highlightthickness=0,
        cursor="hand2", padx=14, pady=6,
    )

    def on_enter(_):
        btn.configure(bg=hover)

    def on_leave(_):
        btn.configure(bg=accent)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


def make_button(parent, text, command=None, accent=ACCENT, **kw):
    btn = tk.Button(parent, text=text, command=command, **kw)
    return style_button(btn, accent=accent)


def make_card(parent, **kw):
    return tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER,
                    highlightthickness=1, **kw)


def make_entry(parent, width=24):
    return tk.Entry(
        parent, font=FONT_BODY, width=width, bg=BG_INPUT, fg=TEXT,
        insertbackground=TEXT, relief="flat", bd=6,
        highlightbackground=BORDER, highlightcolor=ACCENT,
    )


def rounded_rect(canvas, x1, y1, x2, y2, r=14, **kwargs):
    """Draw a rounded rectangle on a canvas; returns the item id."""
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RingProgress:
    """Circular progress ring drawn on a Canvas."""

    def __init__(self, parent, size=120, color=ACCENT):
        self.size = size
        self.color = color
        self.canvas = tk.Canvas(
            parent, width=size, height=size, bg=BG, highlightthickness=0
        )
        c = size // 2
        self._bg_arc = self.canvas.create_arc(
            12, 12, size - 12, size - 12, start=90, extent=359.9,
            style=tk.ARC, width=10, outline=BORDER
        )
        self._fg_arc = self.canvas.create_arc(
            12, 12, size - 12, size - 12, start=90, extent=0,
            style=tk.ARC, width=10, outline=color
        )
        self._text = self.canvas.create_text(
            c, c, text="0%", font=("Segoe UI", 18, "bold"), fill=TEXT
        )

    def set(self, fraction):
        fraction = max(0.0, min(1.0, float(fraction)))
        self.canvas.itemconfig(self._fg_arc, extent=-359.9 * fraction)
        self.canvas.itemconfig(self._text, text=f"{int(fraction * 100)}%")


# ================= animated background =================

class AnimatedBG:
    """Starfield + soft glow particles drifting on a full-window canvas."""

    PARTICLE_COUNT = 42

    def __init__(self, canvas: tk.Canvas, base=None, glow=ACCENT):
        self.canvas = canvas
        self.base = base or BG
        self.glow = glow
        self._particles = []
        self._running = True
        self._tick = 0

        self.canvas.bind("<Configure>", self._on_configure, add="+")

    def _on_configure(self, _event=None):
        self._draw_gradient()
        if not self._particles:
            self._spawn_particles()
            self._animate()

    def _draw_gradient(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            return
        self.canvas.delete("bg_grad")
        # vertical gradient bands
        top = (7, 16, 38)
        bottom = (3, 6, 16)
        bands = 64
        band_h = max(2, h // bands)
        y = 0
        for i in range(bands):
            t = i / (bands - 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            self.canvas.create_rectangle(
                0, y, w, y + band_h + 1,
                fill=f"#{r:02x}{g:02x}{b:02x}", outline="", tags="bg_grad"
            )
            y += band_h
        # soft radial-ish glow blobs (fake with dim ovals)
        for (cx, cy, rad, col) in (
            (w * 0.18, h * 0.12, 180, "#0b2a4a"),
            (w * 0.85, h * 0.8, 220, "#131f4a"),
            (w * 0.55, h * 0.45, 260, "#0a1e3c"),
        ):
            self.canvas.create_oval(
                cx - rad, cy - rad, cx + rad, cy + rad,
                fill=col, outline="", tags="bg_grad"
            )
        # grid lines for sci-fi feel
        step = 48
        for x in range(0, w, step):
            self.canvas.create_line(
                x, 0, x, h, fill="#0a1428", tags="bg_grad"
            )
        for y2 in range(0, h, step):
            self.canvas.create_line(
                0, y2, w, y2, fill="#0a1428", tags="bg_grad"
            )
        self.canvas.tag_lower("bg_grad")

    def _spawn_particles(self):
        w = max(self.canvas.winfo_width(), 100)
        h = max(self.canvas.winfo_height(), 100)
        for _ in range(self.PARTICLE_COUNT):
            x = random.uniform(0, w)
            y = random.uniform(0, h)
            size = random.uniform(1.2, 3.2)
            speed = random.uniform(0.15, 0.7)
            twinkle = random.uniform(0, math.tau)
            bright = random.random() < 0.22
            color = self.glow if bright else "#29406b"
            item = self.canvas.create_oval(
                x - size, y - size, x + size, y + size,
                fill=color, outline="", tags="particle"
            )
            self._particles.append(
                {"id": item, "x": x, "y": y, "s": size,
                 "v": speed, "tw": twinkle, "bright": bright}
            )
        self.canvas.tag_raise("particle")

    def _animate(self):
        if not self._running:
            return
        try:
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
        except tk.TclError:
            return
        self._tick += 1
        for p in self._particles:
            p["y"] -= p["v"]
            p["x"] += math.sin(self._tick * 0.02 + p["tw"]) * 0.25
            if p["y"] < -6:
                p["y"] = h + 6
                p["x"] = random.uniform(0, w)
            size = p["s"] * (1.0 + 0.35 * math.sin(self._tick * 0.05 + p["tw"]))
            try:
                self.canvas.coords(
                    p["id"],
                    p["x"] - size, p["y"] - size,
                    p["x"] + size, p["y"] + size,
                )
            except tk.TclError:
                return
        self.canvas.after(40, self._animate)

    def stop(self):
        self._running = False


class NeonCardButton:
    """Fancy canvas card-button with neon glow on hover."""

    def __init__(self, canvas, x, y, w, h, title, subtitle, accent,
                 command=None, icon=""):
        self.canvas = canvas
        self.x, self.y, self.w, self.h = x, y, w, h
        self.accent = accent
        self.command = command
        self.hover = False
        self._items = []
        self._title, self._subtitle, self._icon = title, subtitle, icon

        self._draw(title, subtitle, icon)

        for item in self._items:
            canvas.tag_bind(item, "<Enter>", self._on_enter)
            canvas.tag_bind(item, "<Leave>", self._on_leave)
            canvas.tag_bind(item, "<Button-1>", self._on_click)

    def _draw(self, title, subtitle, icon):
        c = self.canvas
        x, y, w, h = self.x, self.y, self.w, self.h
        r = 16

        if self.hover:
            # neon outer glows
            for pad, col in ((10, _darken(self.accent, 0.72)),
                             (6, _darken(self.accent, 0.45)),
                             (3, _darken(self.accent, 0.2))):
                self._items.append(rounded_rect(
                    c, x - pad, y - pad, x + w + pad, y + h + pad,
                    r=r + pad, fill=col, outline=""
                ))
            card_bg = BG_INPUT
            arrow_col = self.accent
        else:
            card_bg = BG_CARD
            arrow_col = TEXT_MUTED

        self._items.append(rounded_rect(
            c, x, y, x + w, y + h, r=r, fill=card_bg,
            outline=BORDER if not self.hover else self.accent, width=1
        ))
        # accent side bar
        self._items.append(rounded_rect(
            c, x, y, x + 6, y + h, r=3, fill=self.accent, outline=""
        ))
        self._items.append(c.create_text(
            x + 28, y + h / 2 - 11, text=f"{icon}  {title}",
            font=("Segoe UI", 13, "bold"), fill=TEXT, anchor="w"
        ))
        self._items.append(c.create_text(
            x + 28, y + h / 2 + 14, text=subtitle,
            font=FONT_SMALL, fill=TEXT_MUTED, anchor="w"
        ))
        self._items.append(c.create_text(
            x + w - 22, y + h / 2, text="›",
            font=("Segoe UI", 22, "bold"), fill=arrow_col
        ))

    def _redraw(self):
        for item in self._items:
            self.canvas.delete(item)
        self._items = []
        self._draw(self._title, self._subtitle, self._icon)
        # re-bind events: after delete/create the canvas item ids (and their
        # tags) are new, so the old bindings no longer apply
        for item in self._items:
            self.canvas.tag_bind(item, "<Enter>", self._on_enter)
            self.canvas.tag_bind(item, "<Leave>", self._on_leave)
            self.canvas.tag_bind(item, "<Button-1>", self._on_click)

    def _on_enter(self, _):
        if not self.hover:
            self.hover = True
            self._redraw()

    def _on_leave(self, _):
        if self.hover:
            self.hover = False
            self._redraw()

    def _on_click(self, _):
        if self.command:
            self.command()


class PulseLogo:
    """A breathing neon circle logo drawn on a canvas."""

    def __init__(self, canvas, cx, cy, radius=26, accent=ACCENT, letter="D"):
        self.canvas = canvas
        self.cx, self.cy, self.r = cx, cy, radius
        self.accent = accent
        self.letter = letter
        self._tick = 0
        self._running = True

        self.halo = canvas.create_oval(
            cx - radius - 8, cy - radius - 8,
            cx + radius + 8, cy + radius + 8,
            outline=_darken(accent, 0.6), width=2, fill=""
        )
        self.ring = canvas.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius,
            outline=accent, width=2, fill=_darken(accent, 0.75)
        )
        self.text = canvas.create_text(
            cx, cy, text=letter, font=("Segoe UI", 22, "bold"), fill="#041018"
        )
        self._animate()

    def _animate(self):
        if not self._running:
            return
        self._tick += 1
        pulse = math.sin(self._tick * 0.08)
        grow = 4 + pulse * 4
        try:
            self.canvas.coords(
                self.halo,
                self.cx - self.r - grow, self.cy - self.r - grow,
                self.cx + self.r + grow, self.cy + self.r + grow,
            )
            self.canvas.itemconfig(
                self.halo,
                outline=_mix(self.accent, BG, 0.45 + 0.3 * (pulse + 1) / 2)
            )
        except tk.TclError:
            return
        self.canvas.after(50, self._animate)

    def stop(self):
        self._running = False


# ================= color helpers =================

def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(v))) for v in rgb))


def _lighten(hex_color, amount):
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex((r + (255 - r) * amount,
                        g + (255 - g) * amount,
                        b + (255 - b) * amount))


def _darken(hex_color, amount):
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex((r * (1 - amount), g * (1 - amount), b * (1 - amount)))


def _mix(a, b, t):
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    return _rgb_to_hex((ra + (rb - ra) * t,
                        ga + (gb - ga) * t,
                        ba + (bb - ba) * t))
