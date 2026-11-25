import time, hw
hw.setup_gpio()
for name, pin in [("green LED", hw.PIN_LED_GREEN), ("red LED", hw.PIN_LED_RED),
                  ("buzzer", hw.PIN_BUZZER), ("button lamp", hw.PIN_LAMP)]:
    print("ON:", name); hw.set_out(pin, True); time.sleep(1); hw.set_out(pin, False)
print("Press the button (10 s)...")
end = time.time() + 10
while time.time() < end:
    if hw.button_pressed(): print("BUTTON PRESSED"); time.sleep(0.3)
    time.sleep(0.02)