import numpy as np
from scipy.signal import butter, sosfilt
from scipy.fftpack import dct


# ============================================================
# CONFIGURATION
# ============================================================

SAMPLE_RATE = 16000

LOW_CUT = 300
HIGH_CUT = 3400

PRE_EMPHASIS = 0.97

FRAME_SIZE = 400       # 25 ms
FRAME_STEP = 160       # 10 ms

N_FFT = 512
N_MELS = 40
N_MFCC = 13

EPSILON = 1e-10


# ============================================================
# BAND-PASS FILTER
# ============================================================

FILTER = butter(
    4,
    [LOW_CUT, HIGH_CUT],
    btype="bandpass",
    fs=SAMPLE_RATE,
    output="sos"
)


# ============================================================
# PRECOMPUTED WINDOW
# ============================================================

HAMMING_WINDOW = np.hamming(
    FRAME_SIZE
).astype(np.float32)


# ============================================================
# MEL CONVERSION
# ============================================================

def hz_to_mel(freq):

    return 2595.0 * np.log10(
        1.0 + freq / 700.0
    )


def mel_to_hz(mel):

    return 700.0 * (
        10.0 ** (mel / 2595.0) - 1.0
    )


# ============================================================
# PRECOMPUTED MEL FILTER BANK
# ============================================================

def create_mel_filterbank():

    low_mel = hz_to_mel(
        LOW_CUT
    )

    high_mel = hz_to_mel(
        HIGH_CUT
    )

    mel_points = np.linspace(
        low_mel,
        high_mel,
        N_MELS + 2
    )

    hz_points = mel_to_hz(
        mel_points
    )

    bins = np.floor(
        (N_FFT + 1)
        * hz_points
        / SAMPLE_RATE
    ).astype(int)

    filterbank = np.zeros(
        (
            N_MELS,
            N_FFT // 2 + 1
        ),
        dtype=np.float32
    )

    for m in range(
        1,
        N_MELS + 1
    ):

        left = bins[m - 1]
        center = bins[m]
        right = bins[m + 1]

        if center > left:

            filterbank[
                m - 1,
                left:center
            ] = np.linspace(
                0.0,
                1.0,
                center - left,
                endpoint=False
            )

        if right > center:

            filterbank[
                m - 1,
                center:right
            ] = np.linspace(
                1.0,
                0.0,
                right - center,
                endpoint=False
            )

    return filterbank


MEL_FILTERBANK = (
    create_mel_filterbank()
)


# ============================================================
# PREPROCESSING
# ============================================================

def preprocess_audio(audio):

    audio = np.asarray(
        audio,
        dtype=np.float32
    )

    if audio.size == 0:

        return audio

    # --------------------------------------------------------
    # DC removal
    # --------------------------------------------------------

    audio = (
        audio
        - np.mean(audio)
    )

    # --------------------------------------------------------
    # Pre-emphasis
    # --------------------------------------------------------

    emphasized = np.empty_like(
        audio
    )

    emphasized[0] = audio[0]

    if len(audio) > 1:

        emphasized[1:] = (
            audio[1:]
            - PRE_EMPHASIS
            * audio[:-1]
        )

    # --------------------------------------------------------
    # Band-pass filter
    # --------------------------------------------------------

    filtered = sosfilt(
        FILTER,
        emphasized
    )

    return filtered.astype(
        np.float32,
        copy=False
    )


# ============================================================
# FAST LOG-MEL
# ============================================================

def calculate_log_mel(audio):

    audio = np.asarray(
        audio,
        dtype=np.float32
    )

    if len(audio) < FRAME_SIZE:

        return np.zeros(
            (N_MELS, 1),
            dtype=np.float32
        )

    n_frames = (
        1
        + (
            len(audio)
            - FRAME_SIZE
        )
        // FRAME_STEP
    )

    # --------------------------------------------------------
    # Sliding frames
    # --------------------------------------------------------

    shape = (
        n_frames,
        FRAME_SIZE
    )

    strides = (
        audio.strides[0] * FRAME_STEP,
        audio.strides[0]
    )

    frames = (
        np.lib.stride_tricks
        .as_strided(
            audio,
            shape=shape,
            strides=strides,
            writeable=False
        )
    )

    # --------------------------------------------------------
    # Window
    # --------------------------------------------------------

    frames = (
        frames
        * HAMMING_WINDOW
    )

    # --------------------------------------------------------
    # FFT
    # --------------------------------------------------------

    spectrum = np.fft.rfft(
        frames,
        n=N_FFT,
        axis=1
    )

    power = (
        np.abs(spectrum) ** 2
    )

    # --------------------------------------------------------
    # Mel filter bank
    # --------------------------------------------------------

    mel_energy = (
        MEL_FILTERBANK
        @ power.T
    )

    mel_energy = np.maximum(
        mel_energy,
        EPSILON
    )

    # --------------------------------------------------------
    # Log compression
    # --------------------------------------------------------

    log_mel = (
        10.0
        * np.log10(
            mel_energy
        )
    )

    return log_mel.astype(
        np.float32,
        copy=False
    )


# ============================================================
# MFCC
#
# MFCC = DCT(log-Mel energies)
#
# This is for visualization/analysis.
# The microWakeWord model continues using
# its own compatible feature pipeline.
# ============================================================

def calculate_mfcc(log_mel):

    log_mel = np.asarray(
        log_mel,
        dtype=np.float32
    )

    if log_mel.size == 0:

        return np.zeros(
            (N_MFCC, 1),
            dtype=np.float32
        )

    mfcc = dct(
        log_mel,
        type=2,
        axis=0,
        norm="ortho"
    )

    mfcc = mfcc[
        :N_MFCC,
        :
    ]

    return mfcc.astype(
        np.float32,
        copy=False
    )


# ============================================================
# SIGNAL INFORMATION
# ============================================================

def calculate_signal_info(audio):

    audio = np.asarray(
        audio,
        dtype=np.float32
    )

    if len(audio) == 0:

        return {
            "rms": 0.0,
            "peak": 0.0,
            "duration_ms": 0.0
        }

    rms = float(
        np.sqrt(
            np.mean(
                audio ** 2
            )
        )
    )

    peak = float(
        np.max(
            np.abs(audio)
        )
    )

    duration_ms = (
        len(audio)
        / SAMPLE_RATE
        * 1000.0
    )

    return {
        "rms": rms,
        "peak": peak,
        "duration_ms": duration_ms
    }


# ============================================================
# FEATURE INFORMATION
# ============================================================

def get_feature_info():

    return {

        "sample_rate":
            SAMPLE_RATE,

        "frame_size_ms":
            FRAME_SIZE
            / SAMPLE_RATE
            * 1000.0,

        "frame_step_ms":
            FRAME_STEP
            / SAMPLE_RATE
            * 1000.0,

        "n_fft":
            N_FFT,

        "mel_filters":
            N_MELS,

        "mfcc_coefficients":
            N_MFCC,

        "frequency_range":
            "300-3400 Hz"
    }