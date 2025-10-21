import gpiod
from time import sleep
import requests

BACKEND_BASE_URL = "http://103.249.239.235:8000"
LOCK_STATE_ENDPOINT = f"{BACKEND_BASE_URL.rstrip('/')}/lock/state"
POLL_INTERVAL_SECONDS = 1.0
GPIO_CHIP_NAME = "gpiochip4"
SOLENOID_PIN = 18
ACTIVE_HIGH = True
ON_STATE = 1 if ACTIVE_HIGH else 0
OFF_STATE = 0 if ACTIVE_HIGH else 1


def fetch_lock_state() -> bool:
    try:
        resp = requests.get(LOCK_STATE_ENDPOINT, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and isinstance(data.get("locked"), bool):
            return data["locked"]
    except Exception:
        pass
    return True


def main() -> None:
    chip = gpiod.Chip('gpiochip4')
    solenoid_line = chip.get_line(SOLENOID_PIN)
    solenoid_line.request(
        consumer="solenoid-toggle",
        type=gpiod.LINE_REQ_DIR_OUT,
        default_vals=[OFF_STATE],
    )

    try:
        locked = True
        while True:
            locked = fetch_lock_state()
            solenoid_line.set_value(ON_STATE if locked else OFF_STATE)
            sleep(POLL_INTERVAL_SECONDS)
    finally:
        solenoid_line.set_value(OFF_STATE)
        solenoid_line.release()
        chip.close()


if __name__ == "__main__":
    main()
