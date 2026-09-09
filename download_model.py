"""
Downloads and extracts the small offline English Vosk model (~40MB)
into ./model. Run this once before using main.py or wake_test.py.
"""

import urllib.request
import zipfile
import os
import sys

URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
ZIP_NAME = "model.zip"
EXTRACTED_DIR = "vosk-model-small-en-us-0.15"
FINAL_DIR = "model"

def main():
    if os.path.isdir(FINAL_DIR):
        print(f"'{FINAL_DIR}' already exists - skipping download.")
        return

    print(f"Downloading model from {URL} ...")
    try:
        urllib.request.urlretrieve(URL, ZIP_NAME)
    except Exception as e:
        print(f"Download failed: {e}")
        print("Check your internet connection, or download manually from:")
        print("https://alphacephei.com/vosk/models")
        sys.exit(1)

    print("Extracting...")
    with zipfile.ZipFile(ZIP_NAME, "r") as z:
        z.extractall(".")

    os.rename(EXTRACTED_DIR, FINAL_DIR)
    os.remove(ZIP_NAME)
    print(f"Done. Model ready at ./{FINAL_DIR}")


if __name__ == "__main__":
    main()
