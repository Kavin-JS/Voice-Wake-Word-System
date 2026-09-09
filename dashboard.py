import sounddevice as sd
import vosk
import json
import time
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime

# ==============================
# CONFIGURATION
# ==============================

WAKE_WORD = "astra"
WAKE_PHRASE = "hey astra"
COOLDOWN_SECONDS = 2.0
MODEL_PATH = "model"
SAMPLE_RATE = 16000
LED_ON_DURATION_MS = 2000

# ==============================
# COLOR PALETTE
# ==============================

BG = "#0d1117"
CARD_BG = "#161b22"
CARD_BORDER = "#30363d"
ACCENT = "#58a6ff"
ACCENT_DIM = "#1f3a5c"
GREEN = "#3fb950"
GREEN_DIM = "#1a3d2e"
RED = "#f85149"
RED_DIM = "#3d2426"
GRAY_TEXT = "#8b949e"
WHITE_TEXT = "#e6edf3"
YELLOW = "#d29922"
PURPLE = "#bc8cff"

# ==============================
# SHARED STATE
# ==============================

event_queue = queue.Queue()
stop_flag = threading.Event()

# ==============================
# DETECTION THREAD (unchanged working logic)
# ==============================

def detection_worker():
    vosk.SetLogLevel(-1)
    event_queue.put(("status", "Loading model..."))

    model = vosk.Model(MODEL_PATH)
    grammar = '["astra", "hey astra", "[unk]"]'
    rec = vosk.KaldiRecognizer(model, SAMPLE_RATE, grammar)
    rec.SetWords(True)

    audio_queue = queue.Queue()

    def audio_callback(indata, frames, time_info, status):
        if status:
            event_queue.put(("audio_status", str(status)))
        audio_queue.put(bytes(indata))

    detection_count = 0
    last_detection_time = 0

    event_queue.put(("mic_active", True))
    event_queue.put(("status", "Listening..."))

    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000, dtype="int16",
                                channels=1, callback=audio_callback):
            while not stop_flag.is_set():
                try:
                    data = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                processing_start = time.time()

                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").lower().strip()

                    if text:
                        event_queue.put(("heard", text))

                    detected = (WAKE_WORD in text) or (WAKE_PHRASE in text)

                    if detected:
                        current_time = time.time()
                        if current_time - last_detection_time > COOLDOWN_SECONDS:
                            latency_ms = (time.time() - processing_start) * 1000

                            confidence = "N/A"
                            if "result" in result:
                                matching_words = [w for w in result["result"]
                                                   if w.get("word", "") in ["astra", "hey"]]
                                if matching_words:
                                    confs = [w.get("conf", 0) for w in matching_words]
                                    confidence = f"{sum(confs)/len(confs):.2f}"

                            detection_count += 1
                            last_detection_time = current_time

                            event_queue.put(("detection", {
                                "count": detection_count,
                                "text": text,
                                "confidence": confidence,
                                "latency_ms": latency_ms,
                                "timestamp": datetime.now().strftime("%H:%M:%S")
                            }))
                        else:
                            event_queue.put(("cooldown", True))
    except Exception as e:
        event_queue.put(("error", str(e)))
    finally:
        event_queue.put(("mic_active", False))
        event_queue.put(("status", "Stopped"))


def trigger_action(text):
    try:
        subprocess.Popen(["notify-send", "Voice Activation", f"Wake word detected: '{text}'"])
    except FileNotFoundError:
        print("(notify-send not found — install libnotify or swap trigger_action())")


# ==============================
# SMALL REUSABLE WIDGETS
# ==============================

def make_card(parent, accent=None):
    """A bordered card. If `accent` is given, a thin colored rail is drawn
    down the left edge so each card reads as belonging to a category at a
    glance (mic = blue, listening = green, detection = purple, heard = accent)."""
    outer = tk.Frame(parent, bg=CARD_BORDER)
    body = tk.Frame(outer, bg=CARD_BG)

    if accent:
        rail = tk.Frame(body, bg=accent, width=3)
        rail.pack(side="left", fill="y")

    inner = tk.Frame(body, bg=CARD_BG)
    inner.pack(side="left", fill="both", expand=True)

    body.pack(fill="both", expand=True, padx=1, pady=1)
    return outer, inner


def make_pill(parent, text, bg, fg, font):
    lbl = tk.Label(parent, text=text, bg=bg, fg=fg, font=font,
                    padx=12, pady=4)
    return lbl


def make_section_label(parent, icon, text, font, bg=CARD_BG):
    row = tk.Frame(parent, bg=bg)
    tk.Label(row, text=icon, font=font, bg=bg, fg=GRAY_TEXT).pack(side="left")
    tk.Label(row, text=text, font=font, bg=bg, fg=GRAY_TEXT).pack(side="left", padx=(4, 0))
    return row


def add_hover(button, base_bg, hover_bg):
    """Lighten a button on mouse-over, but only while it's enabled — a
    disabled button keeps its muted look."""
    def on_enter(_e):
        if button["state"] == "normal":
            button.config(bg=hover_bg)

    def on_leave(_e):
        if button["state"] == "normal":
            button.config(bg=base_bg)

    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)


# ==============================
# DASHBOARD UI
# ==============================

class Dashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice Activation System")
        self.root.geometry("560x780")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.thread = None
        self.led_reset_job = None
        self.led_on = False
        self.pulse_job = None
        self.pulse_state = 0
        self.clock_job = None
        self.dots_job = None
        self.dot_count = 0
        self.is_listening = False

        self.title_font = tkfont.Font(family="Helvetica", size=20, weight="bold")
        self.subtitle_font = tkfont.Font(family="Helvetica", size=10)
        self.icon_font = tkfont.Font(family="Helvetica", size=11)
        self.label_font = tkfont.Font(family="Helvetica", size=11)
        self.value_font = tkfont.Font(family="Consolas", size=12, weight="bold")
        self.mono_big = tkfont.Font(family="Consolas", size=13, weight="bold")
        self.pill_font = tkfont.Font(family="Helvetica", size=10, weight="bold")
        self.btn_font = tkfont.Font(family="Helvetica", size=12, weight="bold")
        self.clock_font = tkfont.Font(family="Consolas", size=11)

        # ---------- Header ----------
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=24, pady=(22, 8))

        title_row = tk.Frame(header, bg=BG)
        title_row.pack(fill="x")
        tk.Label(title_row, text="VOICE ACTIVATION SYSTEM", font=self.title_font,
                 bg=BG, fg=WHITE_TEXT).pack(side="left", anchor="w")
        self.clock_label = tk.Label(title_row, text="", font=self.clock_font,
                                     bg=BG, fg=GRAY_TEXT)
        self.clock_label.pack(side="right", anchor="e", pady=(4, 0))

        tk.Label(header, text="Offline wake-word detection · Vosk speech engine",
                 font=self.subtitle_font, bg=BG, fg=GRAY_TEXT).pack(anchor="w", pady=(2, 0))

        # Thin decorative brand strip — purely visual, ties the palette together.
        strip = tk.Canvas(header, height=3, bg=BG, highlightthickness=0)
        strip.pack(fill="x", pady=(12, 0))
        self.root.after(10, lambda: self._draw_strip(strip))

        # ---------- LED Card ----------
        led_outer, led_card = make_card(root, accent=PURPLE)
        led_outer.pack(padx=24, pady=8, fill="x")

        make_section_label(led_card, "💡", "ACTIVITY INDICATOR", self.subtitle_font).pack(
            anchor="w", padx=20, pady=(14, 0))

        self.canvas = tk.Canvas(led_card, width=140, height=140, bg=CARD_BG, highlightthickness=0)
        self.canvas.pack(pady=(6, 6))
        # Three concentric rings give the LED a softer, more premium "glow"
        # than a flat two-tone circle, and give the pulse animation room to breathe.
        self.outer_glow = self.canvas.create_oval(15, 15, 125, 125, fill="#181f28", outline="")
        self.glow = self.canvas.create_oval(30, 30, 110, 110, fill="#21262d", outline="")
        self.core = self.canvas.create_oval(48, 48, 92, 92, fill="#484f58", outline="")

        self.led_status_label = tk.Label(led_card, text="VIRTUAL LED · OFF", font=self.btn_font,
                                          bg=CARD_BG, fg=GRAY_TEXT)
        self.led_status_label.pack(pady=(0, 18))

        # ---------- Status Row (mic + listening) ----------
        status_outer, status_card = make_card(root, accent=ACCENT)
        status_outer.pack(padx=24, pady=8, fill="x")
        status_row = tk.Frame(status_card, bg=CARD_BG)
        status_row.pack(fill="x", padx=20, pady=16)

        mic_block = tk.Frame(status_row, bg=CARD_BG)
        mic_block.pack(side="left", expand=True, fill="x")
        make_section_label(mic_block, "🎙", "MICROPHONE", self.subtitle_font).pack(anchor="w")
        self.mic_pill = make_pill(mic_block, "INACTIVE", RED_DIM, RED, self.pill_font)
        self.mic_pill.pack(anchor="w", pady=(4, 0))

        listen_block = tk.Frame(status_row, bg=CARD_BG)
        listen_block.pack(side="left", expand=True, fill="x")
        make_section_label(listen_block, "👂", "LISTENING STATUS", self.subtitle_font).pack(anchor="w")
        self.listen_pill = make_pill(listen_block, "Stopped", "#21262d", GRAY_TEXT, self.pill_font)
        self.listen_pill.pack(anchor="w", pady=(4, 0))

        # ---------- Detection Card ----------
        det_outer, det_card = make_card(root, accent=YELLOW)
        det_outer.pack(padx=24, pady=8, fill="x")
        det_inner = tk.Frame(det_card, bg=CARD_BG)
        det_inner.pack(fill="x", padx=20, pady=16)

        top_row = tk.Frame(det_inner, bg=CARD_BG)
        top_row.pack(fill="x")
        make_section_label(top_row, "🔎", "DETECTION STATUS", self.subtitle_font).pack(side="left")
        self.detection_pill = make_pill(top_row, "WAITING", "#21262d", GRAY_TEXT, self.pill_font)
        self.detection_pill.pack(side="right")

        tk.Frame(det_inner, bg=CARD_BORDER, height=1).pack(fill="x", pady=14)

        self.rows = {}
        grid = tk.Frame(det_inner, bg=CARD_BG)
        grid.pack(fill="x")

        fields = [
            ("wake_word", "Wake Word", f"'{WAKE_WORD}' / '{WAKE_PHRASE}'"),
            ("confidence", "Confidence", "--"),
            ("latency", "Latency", "-- ms"),
            ("count", "Detection Count", "0"),
            ("last", "Last Detection", "--"),
        ]

        for i, (key, label_text, default) in enumerate(fields):
            r = tk.Frame(grid, bg=CARD_BG)
            r.pack(fill="x", pady=5)
            tk.Label(r, text=label_text, font=self.label_font, bg=CARD_BG,
                     fg=GRAY_TEXT, width=16, anchor="w").pack(side="left")
            val = tk.Label(r, text=default, font=self.value_font, bg=CARD_BG, fg=WHITE_TEXT, anchor="w")
            val.pack(side="left")
            self.rows[key] = val

        # ---------- Heard text ----------
        heard_outer, heard_card = make_card(root, accent=ACCENT)
        heard_outer.pack(padx=24, pady=8, fill="x")
        heard_inner = tk.Frame(heard_card, bg=CARD_BG)
        heard_inner.pack(fill="x", padx=20, pady=12)
        make_section_label(heard_inner, "🗨", "LAST HEARD", self.subtitle_font).pack(anchor="w")
        self.heard_label = tk.Label(heard_inner, text="—", font=("Consolas", 11),
                                     bg=CARD_BG, fg=ACCENT, anchor="w", wraplength=480, justify="left")
        self.heard_label.pack(anchor="w", pady=(4, 0))

        # ---------- Buttons ----------
        btn_frame = tk.Frame(root, bg=BG)
        btn_frame.pack(pady=18)

        self.start_btn = tk.Button(btn_frame, text="▶  START LISTENING", font=self.btn_font,
                                    bg=GREEN, fg="white", padx=18, pady=10,
                                    activebackground="#2ea043", relief="flat", bd=0,
                                    command=self.start_listening, cursor="hand2")
        self.start_btn.pack(side="left", padx=8)
        add_hover(self.start_btn, GREEN, "#56d364")

        self.stop_btn = tk.Button(btn_frame, text="■  STOP LISTENING", font=self.btn_font,
                                   bg="#30363d", fg="#6e7681", padx=18, pady=10,
                                   activebackground=RED, relief="flat", bd=0,
                                   command=self.stop_listening, cursor="hand2", state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        add_hover(self.stop_btn, RED, "#ff7b72")

        # ---------- Footer ----------
        tk.Label(root, text="ASTRA · OFFLINE VOSK ENGINE", font=self.subtitle_font,
                 bg=BG, fg="#4d5560").pack(pady=(0, 14))

        self.tick_clock()
        self.poll_queue()

    # ---------- Decorative helpers ----------
    def _draw_strip(self, canvas):
        """Draw a thin four-color brand strip under the header once the
        canvas has its real width."""
        canvas.delete("all")
        width = canvas.winfo_width() or 512
        colors = [ACCENT, GREEN, YELLOW, PURPLE]
        seg = width / len(colors)
        for i, color in enumerate(colors):
            canvas.create_rectangle(i * seg, 0, (i + 1) * seg, 3, fill=color, outline="")

    def tick_clock(self):
        self.clock_label.config(text=datetime.now().strftime("%H:%M:%S"))
        self.clock_job = self.root.after(1000, self.tick_clock)

    def animate_dots(self):
        if not self.is_listening:
            return
        self.dot_count = (self.dot_count + 1) % 4
        self.listen_pill.config(text="Listening" + "." * self.dot_count)
        self.dots_job = self.root.after(450, self.animate_dots)

    # ---------- LED control ----------
    def set_led(self, on):
        self.led_on = on
        if self.pulse_job:
            self.root.after_cancel(self.pulse_job)
            self.pulse_job = None

        if on:
            self.canvas.itemconfig(self.outer_glow, fill="#0a2413")
            self.canvas.itemconfig(self.glow, fill="#0d3d1a")
            self.canvas.itemconfig(self.core, fill=GREEN)
            self.led_status_label.config(text="VIRTUAL LED · ON", fg=GREEN)
            self.pulse_state = 0
            self._pulse_led()
        else:
            self.canvas.itemconfig(self.outer_glow, fill="#181f28")
            self.canvas.itemconfig(self.glow, fill="#21262d")
            self.canvas.itemconfig(self.core, fill="#484f58")
            self.led_status_label.config(text="VIRTUAL LED · OFF", fg=GRAY_TEXT)
            self.canvas.coords(self.outer_glow, 15, 15, 125, 125)
            self.canvas.coords(self.glow, 30, 30, 110, 110)

    def _pulse_led(self):
        """Soft breathing animation on the outer rings while the LED is lit."""
        if not self.led_on:
            return
        offset = 6 if self.pulse_state % 2 == 0 else 0
        self.canvas.coords(self.outer_glow, 15 - offset, 15 - offset, 125 + offset, 125 + offset)
        self.canvas.coords(self.glow, 30 - offset // 2, 30 - offset // 2, 110 + offset // 2, 110 + offset // 2)
        self.pulse_state += 1
        self.pulse_job = self.root.after(300, self._pulse_led)

    def set_pill(self, widget, text, bg, fg):
        widget.config(text=text, bg=bg, fg=fg)

    # ---------- Controls ----------
    def start_listening(self):
        stop_flag.clear()
        self.thread = threading.Thread(target=detection_worker, daemon=True)
        self.thread.start()
        self.is_listening = True
        self.start_btn.config(state="disabled", bg="#30363d", fg="#6e7681")
        self.stop_btn.config(state="normal", bg=RED, fg="white")

    def stop_listening(self):
        stop_flag.set()
        self.is_listening = False
        if self.dots_job:
            self.root.after_cancel(self.dots_job)
            self.dots_job = None
        self.start_btn.config(state="normal", bg=GREEN, fg="white")
        self.stop_btn.config(state="disabled", bg="#30363d", fg="#6e7681")
        self.set_pill(self.listen_pill, "Stopped", "#21262d", GRAY_TEXT)
        self.set_pill(self.mic_pill, "INACTIVE", RED_DIM, RED)

    def poll_queue(self):
        try:
            while True:
                kind, payload = event_queue.get_nowait()

                if kind == "status":
                    if "Listen" in payload:
                        # Handled by the animated-dots loop instead of a static
                        # label, so the card feels alive while it's active.
                        self.set_pill(self.listen_pill, "Listening", GREEN_DIM, GREEN)
                        if not self.dots_job:
                            self.animate_dots()
                    else:
                        self.set_pill(self.listen_pill, payload, "#21262d", GRAY_TEXT)
                elif kind == "mic_active":
                    if payload:
                        self.set_pill(self.mic_pill, "ACTIVE", GREEN_DIM, GREEN)
                    else:
                        self.set_pill(self.mic_pill, "INACTIVE", RED_DIM, RED)
                elif kind == "heard":
                    self.heard_label.config(text=f'"{payload}"', fg=ACCENT)
                elif kind == "cooldown":
                    pass
                elif kind == "error":
                    self.set_pill(self.listen_pill, "ERROR", RED_DIM, RED)
                elif kind == "detection":
                    self.set_pill(self.detection_pill, "DETECTED ✅", GREEN_DIM, GREEN)
                    self.rows["latency"].config(text=f"{payload['latency_ms']:.1f} ms")

                    conf_color = GRAY_TEXT
                    try:
                        conf_val = float(payload["confidence"])
                        conf_color = GREEN if conf_val >= 0.8 else (YELLOW if conf_val >= 0.5 else RED)
                    except (ValueError, TypeError):
                        pass
                    self.rows["confidence"].config(text=payload["confidence"], fg=conf_color)

                    self.rows["count"].config(text=str(payload["count"]), fg=WHITE_TEXT)
                    self.rows["last"].config(text=payload["timestamp"])

                    self.set_led(True)
                    trigger_action(payload["text"])

                    if self.led_reset_job:
                        self.root.after_cancel(self.led_reset_job)
                    self.led_reset_job = self.root.after(LED_ON_DURATION_MS, self.reset_after_detection)

        except queue.Empty:
            pass

        self.root.after(50, self.poll_queue)

    def reset_after_detection(self):
        self.set_led(False)
        self.set_pill(self.detection_pill, "WAITING", "#21262d", GRAY_TEXT)


if __name__ == "__main__":
    root = tk.Tk()
    app = Dashboard(root)
    root.mainloop()