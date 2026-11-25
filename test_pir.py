import time, hw
hw.setup_gpio()
print("Warming up PIR 60 s, don't move..."); time.sleep(60)
while True:
    print("MOTION" if hw.motion() else "no motion"); time.sleep(0.5)