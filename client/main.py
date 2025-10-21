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
LED_PIN = 17
BUTTON_PIN = 27

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lock-watcher")

chip: gpiod.Chip | None = None
lock_line: gpiod.Line | None = None
led_line: gpiod.Line | None = None
button_line: gpiod.Line | None = None

try:
    chip = gpiod.Chip(GPIO_CHIP_NAME)
    lock_line = chip.get_line(GPIO_PIN)
    led_line = chip.get_line(LED_PIN)
    button_line = chip.get_line(BUTTON_PIN)
    lock_line.request(consumer="lock-watcher", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1])
    led_line.request(consumer="lock-indicator", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
    button_line.request(consumer="lock-button", type=gpiod.LINE_REQ_DIR_IN)
except (OSError, RuntimeError) as exc:
    logger.error("Failed to initialize GPIO line %s/%s: %s", GPIO_CHIP_NAME, GPIO_PIN, exc)
    sys.exit(1)

def cleanup_and_exit(exit_code: int = 0) -> None:
    try:
        if lock_line is not None:
            lock_line.set_value(1)
        if led_line is not None:
            led_line.set_value(0)
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("Failed to preset lines during cleanup: %s", exc)
    finally:
        for line, label in ((lock_line, "lock"), (led_line, "led"), (button_line, "button")):
            if line is not None:
                try:
                    line.release()
                except Exception as release_exc:  # pylint: disable=broad-except
                    logger.debug("Failed to release %s line: %s", label, release_exc)
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
    if led_line is not None:
        led_line.set_value(0 if locked else 1)
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

            button_override = False
            if button_line is not None:
                try:
                    if button_line.get_value() == 1:
                        locked = False
                        button_override = True
                except OSError as exc:
                    logger.debug("Failed to read button state: %s", exc)

            if locked != last_locked:
                apply_lock_state(locked)
                state_text = "locked" if locked else "unlocked"
                if button_override:
                    state_text += " (manual override)"
                logger.info("Lock state changed: %s", state_text)
                last_locked = locked

            sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        cleanup_and_exit(0)


if __name__ == "__main__":
    main()
