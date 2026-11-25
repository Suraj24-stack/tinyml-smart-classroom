import time, RPi.GPIO as GPIO
import hw
from mfrc522 import MFRC522
GPIO.setmode(GPIO.BCM)                       # must be set BEFORE creating the reader
reader = MFRC522(pin_rst=hw.PIN_RC522_RST)

def read_uid():
    status, _ = reader.MFRC522_Request(reader.PICC_REQIDL)
    if status != reader.MI_OK: return None
    status, uid = reader.MFRC522_Anticoll()
    if status != reader.MI_OK: return None
    return "".join(f"{b:02X}" for b in uid[:4])

print("Tap a card or tag...")
try:
    while True:
        uid = read_uid()
        if uid: print("UID:", uid); time.sleep(1)
        time.sleep(0.1)
finally:
    GPIO.cleanup()