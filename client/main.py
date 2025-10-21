import logging
import signal
import sys
from time import sleep
from typing import Any, Dict

import requests
import gpiod

BACKEND_BASE_URL = "http://103.249.239.235:8000"
LOCK_STATE_ENDPOINT = f"{BACKEND_BASE_URL.rstrip('/')}/lock/state"
POLL_INTERVAL_SECONDS = 1.0
GPIO_PIN = 18
GPIO_CHIP_NAME = "gpiochip4"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lock-watcher")

chip: gpiod.Chip | None = None
lock_line: gpiod.Line | None = None

try:
    chip = gpiod.Chip(GPIO_CHIP_NAME)
    lock_line = chip.get_line(GPIO_PIN)
    lock_line.request(consumer="lock-watcher", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1])
except (OSError, RuntimeError) as exc:
    logger.error("Failed to initialize GPIO line %s/%s: %s", GPIO_CHIP_NAME, GPIO_PIN, exc)
    sys.exit(1)

def cleanup_and_exit(exit_code: int = 0) -> None:
    try:
        if lock_line is not None:
            lock_line.set_value(1)
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("Failed to drive line high during cleanup: %s", exc)
    finally:
        if lock_line is not None:
            try:
                lock_line.release()
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Failed to release line: %s", exc)
        if chip is not None:
            chip.close()
    sys.exit(exit_code)


def handle_exit(signum: int, frame: Any) -> None:  # pylint: disable=unused-argument
    logger.info("Received signal %s, cleaning up GPIO and exiting", signum)
    cleanup_and_exit(0)


for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, handle_exit)


def fetch_lock_state() -> Dict[str, Any] | None:
    try:
        resp = requests.get(LOCK_STATE_ENDPOINT, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected lock state payload")
        return data
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Failed to fetch lock state: %s", exc)
        return None


def apply_lock_state(locked: bool) -> None:
    if lock_line is None:
        raise RuntimeError("GPIO line not initialized")
    lock_line.set_value(1 if locked else 0)
    logger.debug("GPIO %s -> %s", GPIO_PIN, "HIGH" if locked else "LOW")


def main() -> None:
    logger.info("Starting lock watcher, polling %s every %.1fs", LOCK_STATE_ENDPOINT, POLL_INTERVAL_SECONDS)
    last_locked: bool | None = None

    try:
        while True:
            payload = fetch_lock_state()
            if payload is not None and isinstance(payload.get("locked"), bool):
                locked = payload["locked"]
            else:
                locked = True

            if locked != last_locked:
                apply_lock_state(locked)
                state_text = "locked" if locked else "unlocked"
                logger.info("Lock state changed: %s", state_text)
                last_locked = locked

            sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        cleanup_and_exit(0)


if __name__ == "__main__":
    main()
