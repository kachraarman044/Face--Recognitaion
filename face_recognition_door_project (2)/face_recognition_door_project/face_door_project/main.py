"""
main.py
Entry point for the Face Recognition Door project.

Run this file to open the main menu:
    python main.py

From the menu you can:
1. Register a new face (webcam captures samples -> trains the model)
2. Start the Door Scanner (live recognition + animated door + voice)
3. Delete a registered user (removes dataset + retrains model)
"""

import os
import shutil
import tkinter as tk
from tkinter import messagebox

import utils
import theme
from register import RegisterWindow
from scanner import ScannerWindow

WIN_W = 640
WIN_H = 720


class MainMenu(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Face Recognition Door")
        self.configure(bg=theme.BG)
        self.resizable(True, True)
        self.minsize(640, 720)

        utils.ensure_dirs()

        # full-window animated background canvas
        self.canvas = tk.Canvas(self, bg=theme.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.bg = theme.AnimatedBG(self.canvas)

        # fixed-size UI panel, centered on the big canvas (rebuilt on resize)
        self._content_w = WIN_W
        self._content_h = WIN_H
        self._resize_job = None
        self.content = tk.Canvas(
            self.canvas, width=WIN_W, height=WIN_H,
            bg=theme.BG, highlightthickness=1,
            highlightbackground=theme.BORDER
        )
        self._content_win = self.canvas.create_window(
            WIN_W / 2, WIN_H / 2, window=self.content, anchor="center"
        )
        self.canvas.bind("<Configure>", self._on_canvas_resize, add="+")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._safe_exit)

        # open maximized
        self.state("zoomed")
        self.after(50, self._center_content)

    # ---------- responsive resize ----------

    def _on_canvas_resize(self, event=None):
        if event is not None and event.widget is not self.canvas:
            return
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except tk.TclError:
                pass
        self._resize_job = self.after(180, self._do_resize)

    def _do_resize(self):
        self._resize_job = None
        try:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
        except tk.TclError:
            return
        if cw <= 1 or ch <= 1:
            return

        # responsive content size: grows with window, keeps sane bounds
        new_w = max(WIN_W, min(980, cw - 80))
        new_h = max(WIN_H, min(WIN_H, ch - 40))  # height stays fixed layout
        resized = (new_w != self._content_w or new_h != self._content_h)

        if resized:
            self._content_w, self._content_h = new_w, new_h
            try:
                self.content.configure(width=new_w, height=new_h)
            except tk.TclError:
                return
            self._rebuild_ui()
        self._center_content()

    def _rebuild_ui(self):
        """Wipe and redraw the UI panel for the current size."""
        if hasattr(self, "logo"):
            self.logo.stop()
        self.content.delete("all")
        self._build_ui()

    def _center_content(self):
        try:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
        except tk.TclError:
            return
        if cw > 1 and ch > 1:
            self.canvas.coords(self._content_win, cw / 2, ch / 2)

    def _build_ui(self):
        c = self.content
        w = self._content_w
        pad = 32
        card_w = w - 2 * pad
        ch = 86

        # ---------- hero ----------
        self.logo = theme.PulseLogo(c, pad + 20, 62, radius=24, letter="D")
        c.create_text(
            pad + 60, 44, text="FACE RECOGNITION DOOR", anchor="w",
            font=("Segoe UI", 19, "bold"), fill=theme.TEXT
        )
        c.create_text(
            pad + 60, 70, text="SMART  LOCK  SYSTEM  //  v2.0", anchor="w",
            font=("Consolas", 10), fill=theme.ACCENT
        )
        c.create_line(pad, 104, w - pad, 104, fill=theme.BORDER)

        # ---------- status card ----------
        theme.rounded_rect(c, pad, 124, w - pad, 210, r=14,
                           fill=theme.BG_CARD, outline=theme.BORDER)
        c.create_text(
            pad + 20, 148, text="●  REGISTERED USERS", anchor="w",
            font=("Consolas", 10, "bold"), fill=theme.ACCENT
        )
        self.users_text_id = c.create_text(
            pad + 20, 180, text="", anchor="w",
            font=theme.FONT_BODY, fill=theme.TEXT_MUTED
        )
        self._refresh_users_label()

        # ---------- action cards (fluid width) ----------
        self.btn_register = theme.NeonCardButton(
            c, pad, 236, card_w, ch,
            "Register New Face", "Capture webcam samples and train the model",
            theme.ACCENT, command=self.open_register, icon="➕"
        )
        self.btn_scanner = theme.NeonCardButton(
            c, pad, 236 + ch + 16, card_w, ch,
            "Start Door Scanner", "Live face recognition + animated door",
            "#3b82f6", command=self.open_scanner, icon="🔍"
        )
        self.btn_delete = theme.NeonCardButton(
            c, pad, 236 + (ch + 16) * 2, card_w, ch,
            "Delete Registered User", "Remove a face and retrain the model",
            theme.DANGER, command=self.open_delete, icon="🗑️"
        )

        # ---------- footer ----------
        footer_y = 236 + (ch + 16) * 3 + 24
        c.create_line(pad, footer_y, w - pad, footer_y, fill=theme.BORDER)
        c.create_text(
            w / 2, footer_y + 30,
            text="OpenCV  •  LBPH  •  Haar Cascade  •  Tkinter",
            font=("Consolas", 9), fill="#3d5478"
        )

        exit_btn = tk.Button(
            self, text="Exit  ✕", command=self._safe_exit,
            bg=theme.BG, fg=theme.TEXT_MUTED, font=("Segoe UI", 10),
            relief="flat", bd=0, cursor="hand2",
            activebackground=theme.BG, activeforeground=theme.TEXT
        )
        self.content.create_window(w / 2, footer_y + 72, window=exit_btn)

        # panel height fits footer
        self._content_h = max(WIN_H, footer_y + 110)
        try:
            self.content.configure(height=self._content_h)
        except tk.TclError:
            pass

    def _safe_exit(self):
        self.logo.stop()
        self.bg.stop()
        self.destroy()

    def _refresh_users_label(self):
        users = utils.list_registered_users()
        if users:
            text = f"{len(users)} user(s) online  →  {', '.join(users)}"
            color = theme.ACCENT
        else:
            text = "No users registered yet. Add your first face."
            color = theme.TEXT_MUTED
        self.content.itemconfig(self.users_text_id, text=text, fill=color)

    def open_register(self):
        RegisterWindow(self, on_done=self._refresh_users_label)

    def open_scanner(self):
        if not utils.list_registered_users():
            messagebox.showwarning(
                "No users", "Please register at least one face before scanning."
            )
            return
        ScannerWindow(self)

    def open_delete(self):
        users = utils.list_registered_users()
        if not users:
            messagebox.showinfo("No Users", "No registered users found to delete.")
            return
        DeleteUserWindow(self, users, on_done=self._refresh_users_label)


class DeleteUserWindow(tk.Toplevel):
    def __init__(self, master, users, on_done=None):
        super().__init__(master)
        self.title("Delete Registered User")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.on_done = on_done

        self._build_ui(users)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build_ui(self, users):
        pad = 16

        tk.Label(
            self, text="🗑️  Delete Registered User", bg=theme.BG, fg=theme.TEXT,
            font=theme.FONT_TITLE
        ).pack(pady=(pad + 6, 4))

        tk.Label(
            self, text="Select a user to permanently delete their\nface data and retrain the model.",
            bg=theme.BG, fg=theme.TEXT_MUTED, font=theme.FONT_SUBTITLE, justify="center"
        ).pack(pady=(0, 14))

        card = theme.make_card(self)
        card.pack(fill="both", expand=True, padx=pad, pady=(0, 12))

        frame = tk.Frame(card, bg=theme.BG_CARD)
        frame.pack(padx=14, pady=14)

        scrollbar = tk.Scrollbar(frame, orient="vertical")
        self.listbox = tk.Listbox(
            frame, font=("Segoe UI", 12), width=28, height=6,
            bg=theme.BG_INPUT, fg=theme.TEXT, selectbackground=theme.DANGER,
            selectforeground="white", relief="flat", bd=0,
            highlightthickness=1, highlightbackground=theme.BORDER,
            yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=self.listbox.yview)
        self.listbox.pack(side="left")
        scrollbar.pack(side="right", fill="y")

        for user in users:
            self.listbox.insert(tk.END, f"  {user}")

        btn_frame = tk.Frame(self, bg=theme.BG)
        btn_frame.pack(pady=(0, pad))

        theme.make_button(
            btn_frame, text="🗑️  Delete Selected", command=self._delete_selected,
            accent=theme.DANGER, width=16
        ).pack(side="left", padx=6)

        theme.make_button(
            btn_frame, text="Cancel", command=self.destroy,
            accent="#475569", width=10
        ).pack(side="left", padx=6)

    def _delete_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a user from the list.", parent=self)
            return

        # Get clean name (strip leading spaces added for display)
        user_name = self.listbox.get(selection[0]).strip()

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete '{user_name}'?\n\nThis will remove all their face images and retrain the model.",
            parent=self
        )
        if not confirm:
            return

        # Delete user dataset folder
        user_dir = utils.user_dataset_path(user_name)
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)

        # Retrain model with remaining users OR remove model if no users left
        remaining_users = utils.list_registered_users()
        if remaining_users:
            try:
                utils.train_model()
                messagebox.showinfo(
                    "Deleted",
                    f"'{user_name}' has been deleted.\nModel retrained with remaining {len(remaining_users)} user(s).",
                    parent=self
                )
            except Exception as e:
                messagebox.showerror("Error", f"Deleted user but retraining failed:\n{e}", parent=self)
        else:
            # No users left — remove stale model files
            for path in [utils.MODEL_PATH, utils.LABELS_PATH]:
                if os.path.exists(path):
                    os.remove(path)
            messagebox.showinfo(
                "Deleted",
                f"'{user_name}' has been deleted.\nNo users remaining — model cleared.",
                parent=self
            )

        if self.on_done:
            self.on_done()
        self.destroy()


if __name__ == "__main__":
    app = MainMenu()
    app.mainloop()
