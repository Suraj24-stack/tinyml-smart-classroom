import time, hw, RPi.GPIO as GPIO
hw.setup_gpio()
while True:
    print(f"DO raw={GPIO.input(hw.PIN_LDR_DO)}  dark={hw.is_dark()}"); time.sleep(0.5)