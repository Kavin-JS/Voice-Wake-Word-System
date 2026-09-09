# Voice Activation System (Wake-Word Detection Prototype)

A working, offline, real-time voice wake-word detection prototype with a live
dashboard, virtual LED, latency measurement, and a triggerable software action.
Built as a laptop-based validation environment for a future ESP32-S3 deployment.

## How it works

```
Laptop Microphone
      |
sounddevice (live audio capture)
      |
Vosk (offline speech recognition, restricted grammar)
      |
Wake-word text match ("astra" / "hey astra")
      |
Confidence + latency measured
      |
Virtual LED ON, notification triggered
      |
Tkinter dashboard updates
```

**Why Vosk instead of a "real" wake-word engine (Porcupine / microWakeWord):**
Vosk is fully offline, needs no API key or account, installs with a single
`pip install`, and ships small pre-trained models with no training step.
It does continuous speech-to-text; the wake word is detected by restricting
its recognition grammar to `["astra", "hey astra", "[unk]"]`, which made
detection of the short name reliable in testing (unrestricted recognition
frequently misheard "astra" as similar-sounding words).

Confidence scores shown in the dashboard are **real per-word confidence
values from Vosk's decoder** (`SetWords(True)`), not invented numbers.

The latency figure shown is **recognition processing time** (time from
final audio chunk to result parsed) - not full microphone-to-GPIO latency.
This is stated honestly in the code and should be described the same way
in a presentation.

## Project structure

```
voice_wake_system/
|-- main.py            <- Full dashboard application (run this for the demo)
|-- wake_test.py        <- Terminal-only detection test (no GUI, for debugging)
|-- mic_test.py          <- Raw microphone hardware test (no speech recognition)
|-- download_model.py     <- One-time script to fetch the offline model
|-- requirements.txt
|-- README.md
```

A flat structure was used deliberately instead of splitting into audio/
detection/ui/utils packages, since a single-file core is more reliable to
debug quickly before a live demo.

## Setup

```bash
cd voice_wake_system

# create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # bash/zsh
# or: source venv/bin/activate.fish   (fish shell)

# install dependencies
pip install -r requirements.txt

# download the offline speech model (~40MB, one-time)
python download_model.py
```

## Verifying each layer (recommended before the demo)

```bash
# 1. Confirm the microphone captures audio at all
python mic_test.py

# 2. Confirm wake-word detection works in the terminal (no GUI)
python wake_test.py
# Say "astra" or "hey astra" a few times, Ctrl+C to stop

# 3. Run the full dashboard
python main.py
```

## Using the dashboard

1. Run `python main.py`
2. Click **START LISTENING**
3. Say **"Hey Astra"** (or just "Astra")
4. Dashboard shows `DETECTED ✅`, the virtual LED turns green, latency and
   confidence are displayed, and a desktop notification fires
5. LED automatically reverts to OFF after ~2 seconds; the system keeps listening
6. Click **STOP LISTENING** to end the session cleanly

## Changing the wake word

Edit the two constants near the top of `main.py` (and `wake_test.py` if you
want the terminal test to match):

```python
WAKE_WORD = "astra"
WAKE_PHRASE = "hey astra"
```

Also update the `grammar` line to include your new word(s):

```python
grammar = '["astra", "hey astra", "[unk]"]'
```

Short or unusual words may need testing - Vosk's small model can misrecognize
uncommon short words even with a restricted grammar.

## Changing the software action

The action triggered on detection lives in one function in `main.py`:

```python
def trigger_action(text):
    subprocess.Popen(["notify-send", "Voice Activation", f"Wake word detected: '{text}'"])
```

It currently fires a Linux desktop notification via `notify-send`. To swap it
for a sound or a webpage, replace the body of this function only - nothing
else in the detection or UI code needs to change. If `notify-send` isn't
available on a machine, install `libnotify` (`sudo pacman -S libnotify` on
Arch/CachyOS, `sudo apt install libnotify-bin` on Debian/Ubuntu), or just
swap the action.

## Troubleshooting

- **`ModuleNotFoundError: No module named '_tkinter'`** - install the OS
  package: `sudo pacman -S tk` (Arch/CachyOS) or `sudo apt install python3-tk`
  (Debian/Ubuntu).
- **`externally-managed-environment` pip error** - you're not inside the venv.
  Run `source venv/bin/activate` (or `.fish` variant) first.
- **No detections despite speaking clearly** - run `mic_test.py` first to
  confirm the hardware mic level isn't near zero (check for OS-level mute).
- **Wake word never triggers / wrong text recognized** - run `wake_test.py`
  and watch the `Heard: '...'` lines to see exactly what Vosk transcribes,
  then adjust `WAKE_WORD`/`WAKE_PHRASE`/`grammar` to match.
- **Vosk model errors on load** - confirm `python download_model.py` was run
  and a `model/` folder exists in the project directory with files inside it.

## Path to ESP32-S3

This prototype validates the detection and response pipeline on a laptop.
For the ESP32-S3 target, the same "wake word detected" event would trigger
a GPIO write (physical LED) instead of the virtual LED and desktop
notification used here. The detection engine itself (Vosk) is not meant to
run on the ESP32-S3 - a lightweight on-device model (e.g. microWakeWord)
would replace it for the embedded deployment; this repo's job is to prove
out the surrounding pipeline logic (capture -> detect -> confidence ->
latency -> action -> dashboard) before that hardware integration work.
