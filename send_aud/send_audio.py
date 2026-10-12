import os
import sys
import time
import logging
from pathlib import Path

from dotenv import load_dotenv

import requests
import audclasslib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MAX_TEXT_CHARS = 4096

# setting max file size to 2 MB
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024

# How long to wait (seconds) after a file appears before sending it,
# to make sure the file has finished being written (e.g. large copies/downloads)
SETTLE_SECONDS = 1.5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("folder-watcher")


def wait_until_stable(path: Path, checks: int = 3, interval: float = 0.5) -> bool:
    """Wait until a file's size stops changing, indicating the write is done."""
    last_size = -1
    stable_count = 0
    for _ in range(60):  # give up after ~30s of waiting
        if not path.exists():
            return False
        size = path.stat().st_size
        if size == last_size:
            stable_count += 1
            if stable_count >= checks:
                return True
        else:
            stable_count = 0
            last_size = size
        time.sleep(interval)
    return True

def send_telegram_message(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        raise ValueError("text must not be empty")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(
            f"text is {len(text)} characters; Telegram allows at most {MAX_TEXT_CHARS}"
        )

    if not BOT_TOKEN or "PUT_YOUR" in BOT_TOKEN:
        log.error("BOT_TOKEN is not configured. Set TELEGRAM_BOT_TOKEN.")
        return
    if not CHAT_ID or "PUT_YOUR" in CHAT_ID:
        log.error("CHAT_ID is not configured. Set TELEGRAM_CHAT_ID.")
        return

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=30,
        )
    except requests.RequestException as exc:
        log.error("sendMessage request failed: %s", exc)
        return False

    try:
        body = resp.json()
        if not isinstance(body, dict):
            raise ValueError(f"expected a JSON object, got {type(body).__name__}")
    except ValueError as exc:
        log.error(
            "sendMessage returned an unusable body (HTTP %s): %s",
            resp.status_code,
            exc,
        )
        return False

    if resp.status_code != 200 or not body.get("ok"):
        log.error(
            "Telegram API error (HTTP %s): %s",
            resp.status_code,
            body.get("description"),
        )
        return False

    log.info("[*] capture message sent")
    return True

def send_file_to_telegram(file_path: Path, classification: str):
    if not BOT_TOKEN or "PUT_YOUR" in BOT_TOKEN:
        log.error("BOT_TOKEN is not configured. Set TELEGRAM_BOT_TOKEN.")
        return
    if not CHAT_ID or "PUT_YOUR" in CHAT_ID:
        log.error("CHAT_ID is not configured. Set TELEGRAM_CHAT_ID.")
        return

    size = file_path.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        log.warning(f"Skipping {file_path.name}: {size} bytes exceeds Telegram's 50MB bot upload limit.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": (file_path.name, f)}
            data = {"chat_id": CHAT_ID, "caption": f"New file: {file_path.name}. Classification: {classification}"}
            resp = requests.post(url, data=data, files=files, timeout=60)
        if resp.ok and resp.json().get("ok"):
            log.info(f"Sent to Telegram: {file_path.name}")
        else:
            log.error(f"Telegram API error for {file_path.name}: {resp.text}")
    except requests.RequestException as e:
        log.error(f"Failed to send {file_path.name}: {e}")


class NewFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        log.info(f"Detected new file: {file_path.name}")
        classification = audclasslib.classify_file(str(file_path))
        print("  [*] classification details: ")
        print(classification)
        # Wait for the file to finish being written before sending it
        if not wait_until_stable(file_path):
            log.warning(f"{file_path.name} disappeared before it could be sent.")
            return
        if classification['label'] != 'backgroundnoise' and classification['top_class'] != 'Silence':
            classmsgtext = f"label: {classification['label']}, top_class: {classification['top_class']}"
            send_file_to_telegram(file_path, classmsgtext)
        #if classification['label'] == 'voice':
        #    print("[!] voice detected - sending capture instruction")
        #    text = "capture"
        #    #send_telegram_message(text)
        os.remove(file_path)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {Path(__file__).name} <folder_to_watch>")
        sys.exit(1)

    watch_dir = Path(sys.argv[1]).expanduser().resolve()
    if not watch_dir.is_dir():
        print(f"Error: {watch_dir} is not a valid directory.")
        sys.exit(1)

    log.info(f"Watching folder: {watch_dir}")
    event_handler = NewFileHandler()
    observer = Observer()
    observer.schedule(event_handler, str(watch_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping watcher...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
