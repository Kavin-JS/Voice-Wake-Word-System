"""
Raw microphone capture test - no speech recognition involved.
Run this first if you ever suspect a mic/hardware issue.
"""

import sounddevice as sd
import numpy as np

print("Recording for 3 seconds... Speak now!")
duration = 3
samplerate = 16000
recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='int16')
sd.wait()

volume = np.abs(recording).mean()
print(f"Done. Average volume level: {volume:.1f}")
if volume < 5:
    print("WARNING: Very low volume detected. Check mic is not muted.")
else:
    print("Mic capture looks good.")
