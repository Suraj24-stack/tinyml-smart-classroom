import time, hw, RPi.GPIO as GPIO
hw.setup_gpio(); ads = hw.ADS1115()
while True:
    print(f"DO raw={GPIO.input(hw.PIN_SOUND_DO)}  level={ads.sound_level():.3f} V")
    time.sleep(0.3)