"""
Terminal-only wake word test (no GUI).
Use this to sanity-check microphone + detection before running main.py.
"""

import sounddevice as sd
import vosk
import json
import time
import queue

WAKE_WORD = "astra"
WAKE_PHRASE = "hey astra"

COOLDOWN_SECONDS = 2.0
MODEL_PATH = "model"
SAMPLE_RATE = 16000

vosk.SetLogLevel(-1)

print("Loading Vosk model...")
model = vosk.Model(MODEL_PATH)

# Restrict recognition to the wake word and wake phrase
grammar = '["astra", "hey astra", "[unk]"]'

rec = vosk.KaldiRecognizer(model, SAMPLE_RATE, grammar)
rec.SetWords(True)

audio_queue = queue.Queue()


def audio_callback(indata, frames, time_info, status):
    """Receive microphone audio and place it in the processing queue."""
    if status:
        print(f"Audio status: {status}")

    audio_queue.put(bytes(indata))


detection_count = 0
last_detection_time = 0


print("\n================================")
print("   VOICE WAKE WORD SYSTEM")
print("================================")
print(f"Wake word: '{WAKE_WORD}'")
print(f"Wake phrase: '{WAKE_PHRASE}'")
print("Listening through laptop microphone...")
print("Say: 'Hey Astra'")
print("Press Ctrl+C to stop.\n")


try:
    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=audio_callback
    ):
        while True:
            data = audio_queue.get()
            processing_start = time.time()

            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "").lower().strip()

                if text:
                    print(f"Heard: '{text}'")

                # Detect either "astra" or "hey astra"
                detected = (
                    WAKE_WORD in text
                    or WAKE_PHRASE in text
                )

                if detected:
                    current_time = time.time()

                    # Prevent repeated detections during cooldown
                    if current_time - last_detection_time > COOLDOWN_SECONDS:

                        latency_ms = (
                            time.time() - processing_start
                        ) * 1000

                        # Calculate confidence for recognized wake words
                        confidence = "N/A"

                        if "result" in result:
                            matching_words = [
                                word
                                for word in result["result"]
                                if word.get("word", "")
                                in ["astra", "hey"]
                            ]

                            if matching_words:
                                confs = [
                                    word.get("conf", 0)
                                    for word in matching_words
                                ]

                                confidence = (
                                    f"{sum(confs) / len(confs):.2f}"
                                )

                        detection_count += 1
                        last_detection_time = current_time

                        print()
                        print("================================")
                        print("   WAKE WORD DETECTED!")
                        print("================================")
                        print(f"Detection #: {detection_count}")
                        print(f"Recognized: '{text}'")
                        print(f"Confidence: {confidence}")
                        print(
                            f"Processing latency: "
                            f"{latency_ms:.1f} ms"
                        )
                        print("Virtual LED: ON")
                        print("================================\n")

                    else:
                        print(
                            "[Cooldown active - detection ignored]"
                        )


except KeyboardInterrupt:

    print("\n\n================================")
    print("SYSTEM STOPPED")
    print("================================")
    print(f"Total detections: {detection_count}")
    print("Virtual LED: OFF")
    print("================================")