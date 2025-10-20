import logging
import signal
import sys
from time import sleep
from typing import Any, Dict

import requests
from gpiozero import OutputDevice

BACKEND_BASE_URL = "http://103.249.239.235:8000"
LOCK_STATE_ENDPOINT = f"{BACKEND_BASE_URL.rstrip('/')}/lock/state"
POLL_INTERVAL_SECONDS = 1.0
GPIO_PIN = 18

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lock-watcher")

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
lock_output = OutputDevice(GPIO_PIN, active_high=True, initial_value=True)


def cleanup_and_exit(exit_code: int = 0) -> None:
    try:
        lock_output.on()
    finally:
        lock_output.close()
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
    if locked:
        lock_output.on()
    else:
        lock_output.off()
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
