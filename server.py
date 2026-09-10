from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory
)

from pathlib import Path
import time


app = Flask(__name__)


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR


# ============================================================
# DETECTION HOLD
# ============================================================

DETECTION_HOLD_SECONDS = 2.5


# ============================================================
# DASHBOARD STATE
# ============================================================

state = {

    "waveform": [],

    "log_mel": [],

    "mfcc": [],

    "probability": 0.0,

    "feature_time_ms": 0.0,

    "inference_time_ms": 0.0,

    "total_time_ms": 0.0,

    "detected": False,

    "detection_count": 0,

    "last_detection_time": 0.0,

    "timestamp": time.time()
}


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def dashboard():

    return send_from_directory(
        FRONTEND_DIR,
        "index.html"
    )


# ============================================================
# STATUS
# ============================================================

@app.route(
    "/status",
    methods=["GET"]
)
def status():

    now = time.time()


    detection_active = (

        now
        - state["last_detection_time"]

        < DETECTION_HOLD_SECONDS

    )


    response = dict(state)

    response["detected"] = (
        detection_active
    )


    return jsonify(
        response
    )


# ============================================================
# LIVE DATA
# ============================================================

@app.route(
    "/live_data",
    methods=["POST"]
)
def live_data():

    global state


    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({

            "success":
                False,

            "error":
                "No JSON data received"

        }), 400


    incoming_detected = bool(
        data.get(
            "detected",
            False
        )
    )


    # ========================================================
    # DETECTION EVENT
    # ========================================================

    if incoming_detected:

        state[
            "detection_count"
        ] += 1

        state[
            "last_detection_time"
        ] = time.time()


    # ========================================================
    # UPDATE STATE
    # ========================================================

    state["waveform"] = (
        data.get(
            "waveform",
            []
        )
    )

    state["log_mel"] = (
        data.get(
            "log_mel",
            []
        )
    )

    state["mfcc"] = (
        data.get(
            "mfcc",
            []
        )
    )

    state["probability"] = float(
        data.get(
            "probability",
            0.0
        )
    )

    state["feature_time_ms"] = float(
        data.get(
            "feature_time_ms",
            0.0
        )
    )

    state["inference_time_ms"] = float(
        data.get(
            "inference_time_ms",
            0.0
        )
    )

    state["total_time_ms"] = float(
        data.get(
            "total_time_ms",
            0.0
        )
    )

    state["timestamp"] = data.get(
        "timestamp",
        time.time()
    )


    return jsonify({

        "success":
            True,

        "detection_count":
            state["detection_count"]

    })


# ============================================================
# HEALTH
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "status":
            "running",

        "service":
            "Low-Latency Speech Processing Server",

        "timestamp":
            time.time()

    })


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    print("=" * 60)

    print(
        "       LOW-LATENCY SPEECH PROCESSING DASHBOARD"
    )

    print("=" * 60)

    print()

    print(
        f"Frontend : {FRONTEND_DIR}"
    )

    print(
        "Server   : http://127.0.0.1:5000"
    )

    print()

    print(
        "Detection events are latched for "
        f"{DETECTION_HOLD_SECONDS} seconds."
    )

    print()

    print(
        "Waiting for real-time microphone data..."
    )

    print("=" * 60)


    app.run(

        host="127.0.0.1",

        port=5000,

        debug=False,

        threaded=True
    )