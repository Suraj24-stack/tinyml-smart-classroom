import time, hw
hw.setup_gpio(); ads = hw.ADS1115()
import RPi.GPIO as GPIO
while True:
    print(f"DO raw={GPIO.input(hw.PIN_FLAME_DO)}  flame={hw.flame_digital()}  AO={ads.flame_voltage():.2f} V")
    time.sleep(0.5)