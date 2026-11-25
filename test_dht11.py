from hw import read_dht11
import time
while True:
    t, h = read_dht11()
    print("DHT11 FAILED" if t is None else f"Temp {t:.1f} C   Humidity {h:.0f} %")
    time.sleep(3)