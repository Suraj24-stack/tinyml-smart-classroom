import time, hw
ads = hw.ADS1115()
print("MQ-2 needs ~3 min warm-up (24-48 h burn-in on first use for stable values).")
while True:
    print(f"MQ-2 output {ads.mq_voltage():.2f} V"); time.sleep(1)