# hw.py - single source of truth for pins and low-level drivers
import glob
import time
import threading
import RPi.GPIO as GPIO
from smbus2 import SMBus

# ---------- BCM pin numbers (physical pin in comment) ----------
PIN_DHT11     = 4    # pin 7  (read through kernel driver, not RPi.GPIO)
PIN_PIR       = 17   # pin 11
PIN_FLAME_DO  = 27   # pin 13
PIN_LDR_DO    = 22   # pin 15
PIN_SOUND_DO  = 23   # pin 16
PIN_RC522_RST = 25   # pin 22  (SPI0 uses pins 19,21,23,24)
PIN_BUTTON    = 5    # pin 29
PIN_LAMP      = 6    # pin 31 (through NPN transistor, 12 V lamp)
PIN_BUZZER    = 13   # pin 33 (through NPN transistor)
PIN_LED_GREEN = 19   # pin 35
PIN_LED_RED   = 26   # pin 37

# ---------- I2C ----------
I2C_BUS   = 1
ADS_ADDR  = 0x48
OLED_ADDR = 0x3C
ADS_CH_MQ, ADS_CH_FLAME, ADS_CH_SOUND = 0, 1, 2
MQ_DIVIDER = 2.0          # two 10k resistors

# ---------- Module logic levels (verify with the test scripts!) ----------
FLAME_ACTIVE_LOW = True   # DO goes LOW when flame is seen
LDR_DARK_HIGH    = True   # DO goes HIGH when dark
SOUND_ACTIVE_HIGH = True  # DO goes HIGH on loud sound (some boards are inverted)

i2c_lock = threading.Lock()

def setup_gpio():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for p in (PIN_PIR, PIN_FLAME_DO, PIN_LDR_DO, PIN_SOUND_DO):
        GPIO.setup(p, GPIO.IN)                      # modules drive these lines
    GPIO.setup(PIN_BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    for p in (PIN_LAMP, PIN_BUZZER, PIN_LED_GREEN, PIN_LED_RED):
        GPIO.setup(p, GPIO.OUT, initial=GPIO.LOW)

def motion():        return GPIO.input(PIN_PIR) == 1
def flame_digital():
    v = GPIO.input(PIN_FLAME_DO)
    return (v == 0) if FLAME_ACTIVE_LOW else (v == 1)
def is_dark():
    v = GPIO.input(PIN_LDR_DO)
    return (v == 1) if LDR_DARK_HIGH else (v == 0)
def loud_sound():
    v = GPIO.input(PIN_SOUND_DO)
    return (v == 1) if SOUND_ACTIVE_HIGH else (v == 0)
def button_pressed(): return GPIO.input(PIN_BUTTON) == 0

def set_out(pin, on): GPIO.output(pin, GPIO.HIGH if on else GPIO.LOW)

# ---------- ADS1115 driver (no extra library needed) ----------
class ADS1115:
    def __init__(self, bus=I2C_BUS, addr=ADS_ADDR):
        self.bus = SMBus(bus)
        self.addr = addr

    def read_voltage(self, ch, fast=False):
        """Single-ended read of channel 0-3, +/-4.096 V range."""
        dr = 0b111 if fast else 0b100                  # 860 or 128 samples/s
        config = (1 << 15) | ((4 + ch) << 12) | (0b001 << 9) | (1 << 8) | (dr << 5) | 0b11
        with i2c_lock:
            self.bus.write_i2c_block_data(self.addr, 0x01, [config >> 8, config & 0xFF])
            time.sleep(0.002 if fast else 0.009)
            for _ in range(20):                         # wait for conversion done
                hi, _ = self.bus.read_i2c_block_data(self.addr, 0x01, 2)
                if hi & 0x80:
                    break
                time.sleep(0.001)
            hi, lo = self.bus.read_i2c_block_data(self.addr, 0x00, 2)
        raw = (hi << 8) | lo
        if raw > 0x7FFF:
            raw -= 0x10000
        return max(0.0, raw * 4.096 / 32768.0)

    def mq_voltage(self):
        """Real MQ-2 output voltage (0-5 V), undoing the divider."""
        return self.read_voltage(ADS_CH_MQ) * MQ_DIVIDER

    def flame_voltage(self):
        return self.read_voltage(ADS_CH_FLAME)

    def sound_level(self, samples=40):
        """Peak-to-peak amplitude of the mic signal, in volts."""
        vals = [self.read_voltage(ADS_CH_SOUND, fast=True) for _ in range(samples)]
        return max(vals) - min(vals)

# ---------- DHT11 through Linux kernel driver ----------
def _dht_dir():
    for d in glob.glob("/sys/bus/iio/devices/iio:device*"):
        try:
            if "dht11" in open(d + "/name").read():
                return d
        except OSError:
            pass
    return None

def read_dht11(retries=5):
    """Returns (temp_C, humidity_pct) or (None, None) if the sensor fails."""
    d = _dht_dir()
    if d is None:
        return None, None
    for _ in range(retries):
        try:
            t = int(open(d + "/in_temp_input").read()) / 1000.0
            h = int(open(d + "/in_humidityrelative_input").read()) / 1000.0
            if -10 <= t <= 60 and 0 <= h <= 100:       # FR-011 range check
                return t, h
        except OSError:                                # checksum/timeout -> retry
            pass
        time.sleep(2.1)                                # DHT11 needs 2 s between reads
    return None, None