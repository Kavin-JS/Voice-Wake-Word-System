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

WAKE_WORD = "jarvis"
WAKE_PHRASE = "hey jarvis"
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
GREEN = "#3fb950"
RED = "#f85149"
GRAY_TEXT = "#8b949e"
WHITE_TEXT = "#e6edf3"
YELLOW = "#d29922"

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
    grammar = '["jarvis", "hey jarvis", "[unk]"]'
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
                                                   if w.get("word", "") in ["jarvis", "hey"]]
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

def make_card(parent):
    outer = tk.Frame(parent, bg=CARD_BORDER)
    inner = tk.Frame(outer, bg=CARD_BG)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    return outer, inner


def make_pill(parent, text, bg, fg, font):
    lbl = tk.Label(parent, text=text, bg=bg, fg=fg, font=font,
                    padx=12, pady=4)
    return lbl


# ==============================
# DASHBOARD UI
# ==============================

class Dashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice Activation System")
        self.root.geometry("560x700")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.thread = None
        self.led_reset_job = None
        self.led_on = False
        self.pulse_job = None
        self.pulse_state = 0

        self.title_font = tkfont.Font(family="Helvetica", size=20, weight="bold")
        self.subtitle_font = tkfont.Font(family="Helvetica", size=10)
        self.label_font = tkfont.Font(family="Helvetica", size=11)
        self.value_font = tkfont.Font(family="Consolas", size=12, weight="bold")
        self.mono_big = tkfont.Font(family="Consolas", size=13, weight="bold")
        self.pill_font = tkfont.Font(family="Helvetica", size=10, weight="bold")
        self.btn_font = tkfont.Font(family="Helvetica", size=12, weight="bold")

        # ---------- Header ----------
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=24, pady=(24, 10))

        tk.Label(header, text="VOICE ACTIVATION SYSTEM", font=self.title_font,
                 bg=BG, fg=WHITE_TEXT).pack(anchor="w")
        tk.Label(header, text="Offline wake-word detection · Vosk speech engine",
                 font=self.subtitle_font, bg=BG, fg=GRAY_TEXT).pack(anchor="w", pady=(2, 0))

        # ---------- LED Card ----------
        led_outer, led_card = make_card(root)
        led_outer.pack(padx=24, pady=10, fill="x")

        self.canvas = tk.Canvas(led_card, width=120, height=120, bg=CARD_BG, highlightthickness=0)
        self.canvas.pack(pady=(20, 6))
        self.glow = self.canvas.create_oval(20, 20, 100, 100, fill="#21262d", outline="")
        self.core = self.canvas.create_oval(35, 35, 85, 85, fill="#484f58", outline="")

        self.led_status_label = tk.Label(led_card, text="VIRTUAL LED · OFF", font=self.btn_font,
                                          bg=CARD_BG, fg=GRAY_TEXT)
        self.led_status_label.pack(pady=(0, 18))

        # ---------- Status Row (mic + listening) ----------
        status_outer, status_card = make_card(root)
        status_outer.pack(padx=24, pady=10, fill="x")
        status_row = tk.Frame(status_card, bg=CARD_BG)
        status_row.pack(fill="x", padx=20, pady=16)

        mic_block = tk.Frame(status_row, bg=CARD_BG)
        mic_block.pack(side="left", expand=True, fill="x")
        tk.Label(mic_block, text="MICROPHONE", font=self.subtitle_font, bg=CARD_BG, fg=GRAY_TEXT).pack(anchor="w")
        self.mic_pill = make_pill(mic_block, "INACTIVE", "#3d2426", RED, self.pill_font)
        self.mic_pill.pack(anchor="w", pady=(4, 0))

        listen_block = tk.Frame(status_row, bg=CARD_BG)
        listen_block.pack(side="left", expand=True, fill="x")
        tk.Label(listen_block, text="LISTENING STATUS", font=self.subtitle_font, bg=CARD_BG, fg=GRAY_TEXT).pack(anchor="w")
        self.listen_pill = make_pill(listen_block, "Stopped", "#21262d", GRAY_TEXT, self.pill_font)
        self.listen_pill.pack(anchor="w", pady=(4, 0))

        # ---------- Detection Card ----------
        det_outer, det_card = make_card(root)
        det_outer.pack(padx=24, pady=10, fill="x")
        det_inner = tk.Frame(det_card, bg=CARD_BG)
        det_inner.pack(fill="x", padx=20, pady=16)

        top_row = tk.Frame(det_inner, bg=CARD_BG)
        top_row.pack(fill="x")
        tk.Label(top_row, text="DETECTION STATUS", font=self.subtitle_font, bg=CARD_BG, fg=GRAY_TEXT).pack(side="left")
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
        heard_outer, heard_card = make_card(root)
        heard_outer.pack(padx=24, pady=10, fill="x")
        heard_inner = tk.Frame(heard_card, bg=CARD_BG)
        heard_inner.pack(fill="x", padx=20, pady=12)
        tk.Label(heard_inner, text="LAST HEARD", font=self.subtitle_font, bg=CARD_BG, fg=GRAY_TEXT).pack(anchor="w")
        self.heard_label = tk.Label(heard_inner, text="—", font=("Consolas", 11),
                                     bg=CARD_BG, fg=ACCENT, anchor="w", wraplength=480, justify="left")
        self.heard_label.pack(anchor="w", pady=(4, 0))

        # ---------- Buttons ----------
        btn_frame = tk.Frame(root, bg=BG)
        btn_frame.pack(pady=20)

        self.start_btn = tk.Button(btn_frame, text="▶  START LISTENING", font=self.btn_font,
                                    bg=GREEN, fg="white", padx=18, pady=10,
                                    activebackground="#2ea043", relief="flat", bd=0,
                                    command=self.start_listening, cursor="hand2")
        self.start_btn.pack(side="left", padx=8)

        self.stop_btn = tk.Button(btn_frame, text="■  STOP LISTENING", font=self.btn_font,
                                   bg="#30363d", fg="#6e7681", padx=18, pady=10,
                                   activebackground=RED, relief="flat", bd=0,
                                   command=self.stop_listening, cursor="hand2", state="disabled")
        self.stop_btn.pack(side="left", padx=8)

        self.poll_queue()

    # ---------- LED control ----------
    def set_led(self, on):
        self.led_on = on
        if on:
            self.canvas.itemconfig(self.glow, fill="#0d3d1a")
            self.canvas.itemconfig(self.core, fill=GREEN)
            self.led_status_label.config(text="VIRTUAL LED · ON", fg=GREEN)
        else:
            self.canvas.itemconfig(self.glow, fill="#21262d")
            self.canvas.itemconfig(self.core, fill="#484f58")
            self.led_status_label.config(text="VIRTUAL LED · OFF", fg=GRAY_TEXT)

    def set_pill(self, widget, text, bg, fg):
        widget.config(text=text, bg=bg, fg=fg)

    # ---------- Controls ----------
    def start_listening(self):
        stop_flag.clear()
        self.thread = threading.Thread(target=detection_worker, daemon=True)
        self.thread.start()
        self.start_btn.config(state="disabled", bg="#30363d", fg="#6e7681")
        self.stop_btn.config(state="normal", bg=RED, fg="white")

    def stop_listening(self):
        stop_flag.set()
        self.start_btn.config(state="normal", bg=GREEN, fg="white")
        self.stop_btn.config(state="disabled", bg="#30363d", fg="#6e7681")
        self.set_pill(self.listen_pill, "Stopped", "#21262d", GRAY_TEXT)
        self.set_pill(self.mic_pill, "INACTIVE", "#3d2426", RED)

    def poll_queue(self):
        try:
            while True:
                kind, payload = event_queue.get_nowait()

                if kind == "status":
                    self.set_pill(self.listen_pill, payload, "#1a3d2e" if "Listen" in payload else "#21262d",
                                  GREEN if "Listen" in payload else GRAY_TEXT)
                elif kind == "mic_active":
                    if payload:
                        self.set_pill(self.mic_pill, "ACTIVE", "#1a3d2e", GREEN)
                    else:
                        self.set_pill(self.mic_pill, "INACTIVE", "#3d2426", RED)
                elif kind == "heard":
                    self.heard_label.config(text=f'"{payload}"')
                elif kind == "cooldown":
                    pass
                elif kind == "error":
                    self.set_pill(self.listen_pill, f"ERROR", "#3d2426", RED)
                elif kind == "detection":
                    self.set_pill(self.detection_pill, "DETECTED ✅", "#1a3d2e", GREEN)
                    self.rows["latency"].config(text=f"{payload['latency_ms']:.1f} ms")
                    self.rows["confidence"].config(text=payload["confidence"])
                    self.rows["count"].config(text=str(payload["count"]))
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