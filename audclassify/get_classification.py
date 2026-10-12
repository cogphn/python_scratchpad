import argparse
import csv
import io
import json
import os
import re
import sys
import wave
from pathlib import Path
import pprint

# --- TensorFlow / tf_keras compatibility shim ---------------------------------
# tf_keras 2.15 calls a private TF API removed in TF >= 2.16; restore it on the
# real module (setattr on the lazy tf.__internal__ facade does not propagate).
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TFHUB_DISABLE_TF1_LEARNING", "1")
import importlib

import tensorflow as tf  # noqa: E402

_tf_internal = importlib.import_module("tensorflow._api.v2.compat.v2.__internal__")
if not hasattr(_tf_internal, "register_load_context_function"):
    _tf_internal.register_load_context_function = lambda fn: None

import tensorflow_hub as hub  # noqa: E402

import numpy as np  # noqa: E402

YAMNET_URL = "https://tfhub.dev/google/yamnet/1"
TARGET_SR = 16000
AUDIO_EXTS = {".wav", ".wave", ".flac", ".mp3", ".ogg", ".m4a", ".aiff", ".aif"}

# Coarse categories. Rules are tried in order; the first match wins for a class.
CATEGORY_RULES = [
    ("alarm", re.compile(
        r"alarm|siren|buzzer|smoke detector|fire alarm|beep|doorbell|ringtone|"
        r"telephone|bell|horn|honk|foghorn|chime|gong|cuckoo|church bell", re.I)),
    ("animal", re.compile(
        r"dog|bark|howl|growl|whimper|meow|purr|hiss|cat|bird|chirp|tweet|"
        r"squawk|cluck|crow|caw|coo|hoot|moo|cattle|livestock|horse|neigh|"
        r"bleat|sheep|goat|pig|frog|cricket|insect|mosquito|bee, wasp|rodents,"
        r" rats|squeal|wild animals|reptile|snake|owl", re.I)),
    ("voice", re.compile(
        r"speech|conversation|narration|monolog|whisper|shout|"
        r"scream|yell|babbl|chatter|mumble|raving|whoop|hubbub|cry|wail", re.I)),
    ("music", re.compile(
        r"music|singing|plucked string|string instrument|guitar|banjo|sitar|"
        r"piano|harpsichord|organ|keyboard \(musical|bowed strings|violin|"
        r"fiddle|cello|string section|viola|harp|brass instrument|trumpet|"
        r"trombone|french horn|wind instrument|woodwind|saxophone|clarinet|"
        r"flute|accordion|harmonica|drum|snare|bass drum|cymbal|hi-hat|tambourine|"
        r"marimba|xylophone|vibraphone|gong|steelpan|maracas|timpani|"
        r"orchestr|percussion|beat|synth|electronic|rock and roll|pop music|"
        r"hip hop|rapping|chant", re.I)),
    ("backgroundnoise", re.compile(
        r"noise|silence|wind|rain|thunderstorm|thunder|water|stream|"
        r"waves, surf|ocean|traffic|roadway|vehicle|engine|idling|motor |"
        r"accelerating, revving|air brake|air conditioning|fan|pump|sink|"
        r"water tap, faucet|toilet flush|trickle, dribble|gush|splash|slosh|"
        r"door|squeak|creak|rustl|rumpl|rubb|shuffle|paper|velcro|zipper|"
        r"whoosh|swish|flutter|cupboard|cutlery|silverware|dishes, pots|"
        r"glass|clatter|clink|static|hum|buzz|tick-tock|ticking|click|"
        r"clank|clang|mechanism|power tool|sawing|drill|hammer|typing|"
        r"mouse \(computing|vibration|rumble|sliding door|drawer|"
        r"runny|microwave|washing machine|vacuum cleaner|blender|"
        r"keys jangling|coin|machinery|frying|sizzl|chopping|"
        r"scraper|whistle \(human|fireworks|gunshot|explosion|"
        r"screech|squeal|whir|whirring|chug|steam|piston|propeller|"
        r"wind noise|howl \(wind|roar|roaring|crackle|whimper", re.I)),
]


def classify_class(display_name: str) -> str:
    for cat, pat in CATEGORY_RULES:
        if pat.search(display_name):
            return cat
    return "unknown"


def read_wav(path: Path):
    """Read any PCM/float WAV via stdlib wave; return (float32 mono [-1,1], sr)."""
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        sw = w.getsampwidth()
        comptype = w.getcomptype()
        raw = w.readframes(w.getnframes())

    if comptype != "NONE":
        raise ValueError(f"unsupported WAV compression: {comptype}")

    if sw == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        val = (b[:, 0].astype(np.int32) |
               (b[:, 1].astype(np.int32) << 8) |
               (b[:, 2].astype(np.int32) << 16))
        val = np.where(val >= 1 << 23, val - (1 << 24), val)
        data = val.astype(np.float32) / 8388608.0
    elif sw == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width: {sw} bytes")

    if nch > 1:
        data = data.reshape(-1, nch).mean(axis=1)
    return data, sr


def to_16k_mono(data: np.ndarray, sr: int) -> np.ndarray:
    if sr != TARGET_SR:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(TARGET_SR, sr)
        data = resample_poly(data, TARGET_SR // g, sr // g)
    return data.astype(np.float32)


def load_class_names(model) -> list:
    path = model.class_map_path().numpy().decode()
    names = []
    with io.open(path, "r", encoding="utf-8") as f:
        header = f.readline()  # index,mid,display_name
        for line in f:
            parts = line.strip().split(",", 2)
            name = parts[2] if len(parts) > 2 else parts[-1]
            names.append(name.strip().strip('"'))
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--infile", type=Path, help="audio file to classify")
    ap.add_argument("-o", "--output", type=Path, default=None,
                    help="output file (default: <input>/../classifications.csv)")
    ap.add_argument("--format", choices=["csv", "ndjson"], default="csv")
    ap.add_argument("--threshold", type=float, default=0.10,
                    help="min aggregated category score, else label=unknown")
    ap.add_argument("--topk", type=int, default=5,
                    help="number of top YAMNet classes to record")
    args = ap.parse_args()

    if not os.path.exists(args.infile):
        sys.exit(f"  [!] file does not exist: {args.input_file}")
    
    file_ext = args.infile.suffix.lower()
    if file_ext not in AUDIO_EXTS:
        sys.exit("  [!] unsupported audio file extension")
        
    out = "file_classification.csv"

    print(f"loading YAMNet from {YAMNET_URL} ...", file=sys.stderr)
    model = hub.load(YAMNET_URL)
    class_names = load_class_names(model)
    cat_of = np.array([classify_class(n) for n in class_names])
    categories = sorted({c for c in cat_of if c != "unknown"})

    rows = []
    f = args.infile
    try:
        wav, sr = read_wav(f)
        wav = to_16k_mono(wav, sr)
        scores, _emb, _logmel = model(wav)
        scores = scores.numpy() if hasattr(scores, "numpy") else np.asarray(scores)
        mean = scores.mean(axis=0)  # (521,)

        cat_scores = {c: float(mean[cat_of == c].sum()) for c in categories}
        label, best = "unknown", 0.0
        if cat_scores:
            best_cat = str(max(cat_scores, key=cat_scores.get))
            best = cat_scores[best_cat]
            if best >= args.threshold:
                label = best_cat

        top_idx = np.argsort(mean)[::-1][: args.topk]
        top = [(class_names[j], float(mean[j])) for j in top_idx]

        result = {
            "file": f.name,
            "label": label,
            "score": round(best, 4),
            "top_class": top[0][0],
            "top_class_score": round(top[0][1], 4),
            "top_classes": "; ".join(f"{n}:{s:.3f}" for n, s in top),
            "duration_s": round(len(wav) / TARGET_SR, 3),
            "sample_rate": sr,
            "peak_rms": round(float(np.sqrt((wav ** 2).mean())), 4),
        }
        rows.append(result)
        pprint.pprint(result)
    except Exception as e:
        rows.append({"file": f.name, "label": "error",
                        "score": None, "top_class": str(e),
                        "top_class_score": None, "top_classes": "",
                        "duration_s": None, "sample_rate": None, "peak_rms": None})
        print(f"{f.name}: ERROR {e}", file=sys.stderr)
    #

    with open(out, "w", newline="", encoding="utf-8") as fh:
        if args.format == "ndjson":
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        else:
            wtr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            wtr.writeheader()
            wtr.writerows(rows)

    from collections import Counter
    dist = Counter(r["label"] for r in rows)
    print(f"\nwrote {out} ({len(rows)} files)")
    print("label distribution:", dict(dist))


if __name__ == "__main__":
    main()
