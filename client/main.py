import gpiod
from time import sleep

GPIO_CHIP_NAME = "gpiochip4"
SOLENOID_PIN = 18
ACTIVE_HIGH = True
ON_STATE = 1 if ACTIVE_HIGH else 0
OFF_STATE = 0 if ACTIVE_HIGH else 1


def main() -> None:
    chip = gpiod.Chip('gpiochip4')
    solenoid_line = chip.get_line(SOLENOID_PIN)
    solenoid_line.request(
        consumer="solenoid-toggle",
        type=gpiod.LINE_REQ_DIR_OUT,
        default_vals=[OFF_STATE],
    )

    try:
        while True:
            solenoid_line.set_value(OFF_STATE)
            sleep(1)
            solenoid_line.set_value(ON_STATE)
            sleep(1)
    finally:
        solenoid_line.set_value(OFF_STATE)
        solenoid_line.release()
        chip.close()


if __name__ == "__main__":
    main()
