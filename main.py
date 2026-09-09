import sounddevice as sd
import vosk
import json
import time
import queue
import threading
import subprocess
import sys
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
# SHARED STATE (thread-safe queue)
# ==============================

event_queue = queue.Queue()
stop_flag = threading.Event()

# ==============================
# DETECTION THREAD
# ==============================

def detection_worker():
    vosk.SetLogLevel(-1)
    event_queue.put(("status", "Loading model..."))

    try:
        model = vosk.Model(MODEL_PATH)
    except Exception as e:
        event_queue.put(("error", f"Model load failed: {e}"))
        event_queue.put(("mic_active", False))
        event_queue.put(("status", "Stopped"))
        return

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
                                    confidence = f"{sum(confs) / len(confs):.2f}"

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


# ==============================
# SOFTWARE ACTION
# Swap this function to change what happens on detection
# (e.g. play a sound, open a webpage) without touching detection logic.
# ==============================

def trigger_action(text):
    try:
        subprocess.Popen(["notify-send", "Voice Activation", f"Wake word detected: '{text}'"])
    except FileNotFoundError:
        print("(notify-send not found - install libnotify, or edit trigger_action() in main.py)")


# ==============================
# DASHBOARD UI
# ==============================

class Dashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice Activation System")
        self.root.geometry("520x640")
        self.root.configure(bg="#1a1a2e")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.thread = None
        self.led_reset_job = None

        title_font = tkfont.Font(family="Helvetica", size=18, weight="bold")
        label_font = tkfont.Font(family="Helvetica", size=13)
        value_font = tkfont.Font(family="Helvetica", size=13, weight="bold")
        led_font = tkfont.Font(family="Helvetica", size=48)

        tk.Label(root, text="VOICE ACTIVATION SYSTEM", font=title_font,
                 bg="#1a1a2e", fg="#00d9ff").pack(pady=(20, 10))

        self.led_label = tk.Label(root, text="\u25cf", font=led_font, bg="#1a1a2e", fg="#555555")
        self.led_label.pack(pady=10)
        self.led_text = tk.Label(root, text="Virtual LED: OFF", font=value_font,
                                  bg="#1a1a2e", fg="#ffffff")
        self.led_text.pack()

        info_frame = tk.Frame(root, bg="#16213e", padx=20, pady=15)
        info_frame.pack(pady=20, padx=20, fill="x")

        self.rows = {}
        fields = [
            ("mic", "Microphone:", "INACTIVE"),
            ("listening", "Listening Status:", "Stopped"),
            ("wake_word", "Wake Word:", f"'{WAKE_WORD}' / '{WAKE_PHRASE}'"),
            ("detection_status", "Detection Status:", "WAITING"),
            ("latency", "Latency:", "-- ms"),
            ("confidence", "Confidence:", "--"),
            ("count", "Detection Count:", "0"),
            ("last", "Last Detection:", "--"),
        ]

        for key, label_text, default in fields:
            row = tk.Frame(info_frame, bg="#16213e")
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label_text, font=label_font, bg="#16213e",
                     fg="#aaaaaa", width=18, anchor="w").pack(side="left")
            val_label = tk.Label(row, text=default, font=value_font,
                                  bg="#16213e", fg="#ffffff", anchor="w")
            val_label.pack(side="left")
            self.rows[key] = val_label

        self.heard_label = tk.Label(root, text="Heard: --", font=("Helvetica", 11, "italic"),
                                     bg="#1a1a2e", fg="#888888", wraplength=460)
        self.heard_label.pack(pady=(5, 15))

        btn_frame = tk.Frame(root, bg="#1a1a2e")
        btn_frame.pack(pady=10)

        self.start_btn = tk.Button(btn_frame, text="START LISTENING", font=value_font,
                                    bg="#0f9d58", fg="white", padx=20, pady=10,
                                    command=self.start_listening, relief="flat", cursor="hand2")
        self.start_btn.pack(side="left", padx=10)

        self.stop_btn = tk.Button(btn_frame, text="STOP LISTENING", font=value_font,
                                   bg="#d93025", fg="white", padx=20, pady=10,
                                   command=self.stop_listening, relief="flat", state="disabled",
                                   cursor="hand2")
        self.stop_btn.pack(side="left", padx=10)

        self.poll_queue()

    def start_listening(self):
        stop_flag.clear()
        self.rows["detection_status"].config(text="WAITING", fg="#ffffff")
        self.rows["latency"].config(text="-- ms")
        self.thread = threading.Thread(target=detection_worker, daemon=True)
        self.thread.start()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def stop_listening(self):
        stop_flag.set()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.rows["listening"].config(text="Stopped")
        self.rows["mic"].config(text="INACTIVE", fg="#ff5555")

    def set_led(self, on):
        if on:
            self.led_label.config(fg="#00ff00")
            self.led_text.config(text="Virtual LED: ON")
        else:
            self.led_label.config(fg="#555555")
            self.led_text.config(text="Virtual LED: OFF")

    def poll_queue(self):
        try:
            while True:
                kind, payload = event_queue.get_nowait()

                if kind == "status":
                    self.rows["listening"].config(text=payload)
                elif kind == "mic_active":
                    if payload:
                        self.rows["mic"].config(text="ACTIVE", fg="#00ff00")
                    else:
                        self.rows["mic"].config(text="INACTIVE", fg="#ff5555")
                elif kind == "heard":
                    self.heard_label.config(text=f"Heard: '{payload}'")
                elif kind == "cooldown":
                    pass
                elif kind == "error":
                    self.rows["listening"].config(text=f"ERROR: {payload}")
                    print(f"ERROR: {payload}", file=sys.stderr)
                elif kind == "detection":
                    self.rows["detection_status"].config(text="DETECTED \u2705", fg="#00ff00")
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
        self.rows["detection_status"].config(text="WAITING", fg="#ffffff")

    def on_close(self):
        stop_flag.set()
        self.root.after(150, self.root.destroy)


if __name__ == "__main__":
    root = tk.Tk()
    app = Dashboard(root)
    root.mainloop()
