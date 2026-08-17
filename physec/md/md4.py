import json
import os
import time
import threading
from datetime import datetime

import cv2
import requests

CONFIG_PATH = "md3.config.json"
CLIP_SECONDS = 5
MIN_CONTOUR_AREA = 10000
OUTPUT_DIR = "/media/lh3/motiondetect"
COOLDOWN_SECONDS = 5  # ignore new triggers for this long after a clip starts


def load_config(path):
    with open(path) as f:
        return json.load(f)


def send_video_to_telegram(filepath, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    try:
        with open(filepath, "rb") as video_file:
            resp = requests.post(
                url,
                data={"chat_id": chat_id},
                files={"video": video_file},
                timeout=60,
            )
        if not resp.ok:
            print(f"[!] Telegram error: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[!] error sending to telegram: {e}")
    finally:
        try:
            os.remove(filepath)
        except OSError:
            pass


def record_clip(video, seconds, fps, frame_size, out_path):
    """Record `seconds` worth of frames from `video` to out_path."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, frame_size)
    frames_needed = int(fps * seconds)
    for _ in range(frames_needed):
        ok, frame = video.read()
        if not ok:
            break
        writer.write(frame)
    writer.release()


def main():
    config = load_config(CONFIG_PATH)
    token = config["t_token"]
    chat_id = config["t_chatid"]

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    video = cv2.VideoCapture(0)
    if not video.isOpened():
        raise RuntimeError("could not open video device 0")

    fps = video.get(cv2.CAP_PROP_FPS) or 20.0
    width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))

    static_back = None
    last_trigger = 0.0

    print("[*] running...")
    try:
        while True:
            ok, frame = video.read()
            if not ok:
                print("[!] failed to read frame")
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if static_back is None:
                static_back = gray
                continue

            diff = cv2.absdiff(static_back, gray)
            thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            contours, _ = cv2.findContours(
                thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # Keep the background reference current so lighting drift
            # doesn't accumulate into false positives.
            static_back = gray

            motion_detected = any(
                cv2.contourArea(c) >= MIN_CONTOUR_AREA for c in contours
            )

            now = time.time()
            if motion_detected and (now - last_trigger) > COOLDOWN_SECONDS:
                last_trigger = now
                ts = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
                clip_path = os.path.join(OUTPUT_DIR, f"motion_{ts}.mp4")
                print(f"[*] motion detected, recording {CLIP_SECONDS}s clip -> {clip_path}")

                # Recording blocks the loop for CLIP_SECONDS while it reads
                # frames directly from `video` — this is the clip itself.
                record_clip(video, CLIP_SECONDS, fps, (width, height), clip_path)

                threading.Thread(
                    target=send_video_to_telegram,
                    args=(clip_path, token, chat_id),
                    daemon=True,
                ).start()

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
    except KeyboardInterrupt:
        print("[!] ctrl+c received - shutting down...")
    finally:
        video.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
