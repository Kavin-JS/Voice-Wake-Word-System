"""
Astra wake-word detector + live dashboard feed.
Detection: Vosk offline speech recognition, restricted grammar
(the same logic verified working in wake_test.py).
Visualization: signal_processor.py's DSP (waveform/log-mel/MFCC) —
real signal processing, no missing-model dependency.
"""

import time
import json
import queue
import threading

import numpy as np
import requests
import sounddevice as sd
import vosk

from signal_processor import (
    preprocess_audio,
    calculate_log_mel,
    calculate_mfcc,
    get_feature_info
)

WAKE_WORD = "astra"
WAKE_PHRASE = "hey astra"
COOLDOWN_SECONDS = 2.0
MODEL_PATH = "model"
SAMPLE_RATE = 16000
BLOCK_SAMPLES = 1600  # 100ms per chunk
SERVER_URL = "http://127.0.0.1:5000"

audio_queue = queue.Queue(maxsize=100)
last_detection_time = 0.0
detection_count = 0

print("=" * 60)
print("        ASTRA WAKE-WORD SYSTEM (Vosk engine)")
print("=" * 60)
print("\nLoading Vosk model...")

vosk.SetLogLevel(-1)
vosk_model = vosk.Model(MODEL_PATH)
grammar = f'["{WAKE_WORD}", "{WAKE_PHRASE}", "[unk]"]'
recognizer = vosk.KaldiRecognizer(vosk_model, SAMPLE_RATE, grammar)
recognizer.SetWords(True)
print("[MODEL] Vosk model loaded successfully")
print(f"[MODEL] Wake word: '{WAKE_WORD}' / '{WAKE_PHRASE}'\n")


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"\n[AUDIO] {status}")
    try:
        audio_queue.put_nowait(bytes(indata))
    except queue.Full:
        pass


def send_dashboard_data(payload):
    # Fire in its own thread so a slow/failed HTTP call never blocks
    # the audio/detection loop — this was a real risk in the original
    # alexa_detector.py, which posted synchronously inline.
    def _post():
        try:
            requests.post(f"{SERVER_URL}/live_data", json=payload, timeout=0.3)
        except requests.RequestException:
            pass
    threading.Thread(target=_post, daemon=True).start()


def process_audio():
    global last_detection_time, detection_count
    visualization_buffer = np.zeros(8000, dtype=np.float32)

    while True:
        raw_bytes = audio_queue.get()

        int16_samples = np.frombuffer(raw_bytes, dtype=np.int16)
        float_samples = int16_samples.astype(np.float32) / 32768.0

        n = len(float_samples)
        if n >= len(visualization_buffer):
            visualization_buffer[:] = float_samples[-len(visualization_buffer):]
        else:
            visualization_buffer[:-n] = visualization_buffer[n:]
            visualization_buffer[-n:] = float_samples

        feature_start = time.perf_counter_ns()
        processed = preprocess_audio(visualization_buffer)
        log_mel = calculate_log_mel(processed)
        mfcc = calculate_mfcc(log_mel)
        feature_time_ms = (time.perf_counter_ns() - feature_start) / 1_000_000.0

        inference_start = time.perf_counter_ns()
        detected = False
        confidence = 0.0
        heard_text = ""

        if recognizer.AcceptWaveform(raw_bytes):
            result = json.loads(recognizer.Result())
            heard_text = result.get("text", "").lower().strip()
            is_match = (WAKE_WORD in heard_text) or (WAKE_PHRASE in heard_text)

            if is_match:
                now = time.time()
                if now - last_detection_time > COOLDOWN_SECONDS:
                    matching = [w for w in result.get("result", [])
                                if w.get("word", "") in (WAKE_WORD, "hey")]
                    confidence = (sum(w.get("conf", 0) for w in matching) / len(matching)
                                  if matching else 1.0)
                    detected = True
                    detection_count += 1
                    last_detection_time = now

        inference_time_ms = (time.perf_counter_ns() - inference_start) / 1_000_000.0
        total_time_ms = feature_time_ms + inference_time_ms

        print(f"\rProbability: {confidence:.3f} | DSP: {feature_time_ms:.2f} ms | "
              f"Vosk: {inference_time_ms:.2f} ms | TOTAL: {total_time_ms:.2f} ms",
              end="", flush=True)

        if detected:
            print(f"\n{'='*60}\n               ASTRA DETECTED!\n{'='*60}")
            print(f"Heard: '{heard_text}' | Confidence: {confidence:.2f} | "
                  f"Total: {total_time_ms:.2f} ms\n{'='*60}")

        send_dashboard_data({
            "waveform": visualization_buffer[::20].tolist(),
            "log_mel": log_mel[:, ::2].tolist(),
            "mfcc": mfcc[:, ::2].tolist(),
            "probability": confidence,
            "feature_time_ms": feature_time_ms,
            "inference_time_ms": inference_time_ms,
            "total_time_ms": total_time_ms,
            "detected": detected,
            "timestamp": time.time()
        })


def main():
    info = get_feature_info()
    print("Signal processing configuration:")
    for k, v in info.items():
        print(f"  {k}: {v}")
    print()

    threading.Thread(target=process_audio, daemon=True).start()

    print("Starting microphone... Say 'Hey Astra'. Press Ctrl+C to stop.")
    print("-" * 60)
    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SAMPLES,
                                dtype="int16", channels=1, callback=audio_callback):
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nSystem stopped.")
    except Exception as e:
        print(f"\n[ERROR] {e}")


if __name__ == "__main__":
    main()
