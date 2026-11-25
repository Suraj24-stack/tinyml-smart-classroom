import threading, time, datetime, signal, sys, logging
import RPi.GPIO as GPIO
import hw, db
from fire_model import FireModel
from wifi_monitor import WifiMonitor
from mfrc522 import MFRC522
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas

CLASS_ID = "BCT-3A"          # current class session (FR-004/005)
SENSOR_PERIOD = 3            # seconds
WIFI_PERIOD = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smartclass")
now = lambda: datetime.datetime.now().isoformat(timespec="seconds")

state = {"fire": "STARTING", "wifi": "STARTING", "temp": None, "hum": None,
         "mq": None, "present": 0, "last_scan": "", "alarm": False, "silenced": False}
lock = threading.Lock()
stop = threading.Event()

def add_alert(con, typ, sev, msg, source):
    con.execute("INSERT INTO alerts(type,severity,timestamp,message,source) VALUES(?,?,?,?,?)",
                (typ, sev, now(), msg, source)); con.commit()

# ---------------- RFID attendance thread ----------------
def rfid_loop():
    con = db.connect()
    reader = MFRC522(pin_rst=hw.PIN_RC522_RST)
    last_uid, last_t = None, 0
    while not stop.is_set():
        st, _ = reader.MFRC522_Request(reader.PICC_REQIDL)
        if st == reader.MI_OK:
            st, u = reader.MFRC522_Anticoll()
            if st == reader.MI_OK:
                uid = "".join(f"{b:02X}" for b in u[:4])
                if uid != last_uid or time.time() - last_t > 5:
                    last_uid, last_t = uid, time.time()
                    handle_scan(con, uid)
        time.sleep(0.1)

def handle_scan(con, uid):
    row = con.execute("""SELECT s.student_id, s.name FROM rfid_cards r JOIN students s
                         ON s.student_id=r.student_id WHERE r.rfid_uid=? AND r.status='active'
                         AND s.status='active'""", (uid,)).fetchone()
    d = datetime.date.today().isoformat(); t = datetime.datetime.now().strftime("%H:%M:%S")
    if row is None:                                                    # FR-003
        add_alert(con, "UNKNOWN_RFID", "low", f"Unregistered card {uid}", "rfid")
        msg = "Unknown card"; beep(0.6)
    else:
        cur = con.execute("INSERT OR IGNORE INTO attendance(student_id,class_id,date,time) "
                          "VALUES(?,?,?,?)", (row["student_id"], CLASS_ID, d, t))
        con.commit()
        msg = f"Welcome {row['name'][:12]}" if cur.rowcount else f"Already in: {row['name'][:9]}"
        beep(0.1)
    cnt = con.execute("SELECT COUNT(*) FROM attendance WHERE class_id=? AND date=?",
                      (CLASS_ID, d)).fetchone()[0]
    with lock: state["last_scan"], state["present"] = msg, cnt
    log.info("RFID %s -> %s", uid, msg)

def beep(sec):
    if state["alarm"]: return
    hw.set_out(hw.PIN_BUZZER, True); time.sleep(sec); hw.set_out(hw.PIN_BUZZER, False)

# ---------------- Sensors + fire TinyML thread ----------------
def sensor_loop():
    con = db.connect(); ads = hw.ADS1115(); model = FireModel()
    log.info("Fire model: %s %s", model.kind, model.version)
    prev_t, prev_time = None, time.time()
    mq_fail_reported = dht_fail_reported = False
    while not stop.is_set():
        t, h = hw.read_dht11(retries=2)
        try:
            mq, fv, snd = ads.mq_voltage(), ads.flame_voltage(), ads.sound_level()
            adc_ok = True
        except OSError:
            mq = fv = snd = None; adc_ok = False
        fdo = 1 if hw.flame_digital() else 0

        # FR-011 / NFR-005: missing sensors become alerts, never "normal"
        if t is None and not dht_fail_reported:
            add_alert(con, "SENSOR_FAILURE", "high", "DHT11 not responding", "dht11"); dht_fail_reported = True
        if not adc_ok and not mq_fail_reported:
            add_alert(con, "SENSOR_FAILURE", "high", "ADS1115 / analog sensors offline", "ads1115"); mq_fail_reported = True
        if t is not None: dht_fail_reported = False
        if adc_ok: mq_fail_reported = False

        rate = 0.0
        if t is not None and prev_t is not None:
            rate = (t - prev_t) / max(1e-3, (time.time() - prev_time) / 60)
        if t is not None: prev_t, prev_time = t, time.time()

        if t is not None and adc_ok:
            feats = {"temperature": t, "humidity": h, "mq_v": mq, "flame_v": fv,
                     "flame_do": fdo, "temp_rate": rate}
            label, score, ms = model.predict(feats)                    # FR-012
            con.execute("INSERT INTO ml_predictions(model_type,model_version,timestamp,label,score,latency_ms)"
                        " VALUES('fire',?,?,?,?,?)", (model.version, now(), label, score, ms))
        elif fdo:
            label, score = "HIGH_FIRE_RISK", 0.6   # flame alone, degraded mode
        else:
            label, score = "SENSOR_UNAVAILABLE", 0.0

        con.execute("""INSERT INTO sensor_readings(timestamp,temperature,humidity,smoke,flame,flame_do,
                       sound,dark,motion,label) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (now(), t, h, mq, fv, fdo, snd, int(hw.is_dark()), int(hw.motion()), label))
        con.commit()

        with lock:
            was = state["fire"]
            state.update(fire=label, temp=t, hum=h, mq=mq)
            if label == "HIGH_FIRE_RISK" and was != "HIGH_FIRE_RISK":   # FR-013
                state["alarm"], state["silenced"] = True, False
                add_alert(con, "HIGH_FIRE_RISK", "critical",
                          f"Fire risk: T={t} MQ={mq} flame={fdo} score={score:.2f}", "fire_model")
            elif label == "SMOKE_HEAT_ANOMALY" and was == "NORMAL":
                add_alert(con, "SMOKE_HEAT_ANOMALY", "high", f"Smoke/heat anomaly T={t} MQ={mq}", "fire_model")
            if label == "NORMAL": state["alarm"] = False
        time.sleep(SENSOR_PERIOD)

# ---------------- Wi-Fi anomaly thread ----------------
def wifi_loop():
    con = db.connect(); mon = WifiMonitor()
    while not stop.is_set():
        f = mon.features(); label, score = mon.classify(f)
        con.execute("""INSERT INTO wifi_metrics(timestamp,packet_rate,retry_rate,rssi,mgmt_rate,
                       channel_utilization) VALUES(?,?,?,?,?,?)""",
                    (now(), f["packet_rate"], f["retry_rate"], f["rssi"], f["mgmt_rate"], f["channel_utilization"]))
        if label != "LEARNING":
            con.execute("INSERT INTO ml_predictions(model_type,model_version,timestamp,label,score)"
                        " VALUES('wifi',?,?,?,?)", (mon.version, now(), label, score))
        if label in ("INTERFERENCE", "SUSPICIOUS_ACTIVITY") and state["wifi"] != label:
            add_alert(con, "WIFI_" + label, "medium" if label == "INTERFERENCE" else "high",
                      f"Wi-Fi {label} score={score:.2f} rssi={f['rssi']}", "wifi_monitor")
        con.commit()
        with lock: state["wifi"] = label
        time.sleep(WIFI_PERIOD)

# ---------------- Alarm outputs + button + OLED (main thread) ----------------
def ui_loop():
    oled = None
    try: oled = ssd1306(i2c(port=1, address=hw.OLED_ADDR), width=128, height=64)
    except Exception as e: log.warning("OLED not available: %s", e)
    blink = False
    while not stop.is_set():
        with lock: s = dict(state)
        if hw.button_pressed() and s["alarm"]:                       # acknowledge
            with lock: state["silenced"] = True
            log.info("Alarm silenced by button")
        blink = not blink
        hw.set_out(hw.PIN_BUZZER, s["alarm"] and not s["silenced"] and blink)   # FR-014
        hw.set_out(hw.PIN_LAMP, s["alarm"] and blink)
        hw.set_out(hw.PIN_LED_RED, s["fire"] not in ("NORMAL",) or s["wifi"] not in ("NORMAL", "LEARNING"))
        hw.set_out(hw.PIN_LED_GREEN, s["fire"] == "NORMAL")
        if oled:
            try:
                with hw.i2c_lock, canvas(oled) as d:
                    d.text((0, 0),  f"Present: {s['present']}", fill="white")
                    tt = "--" if s["temp"] is None else f"{s['temp']:.0f}C {s['hum']:.0f}%"
                    d.text((0, 12), f"Env: {tt}", fill="white")
                    d.text((0, 24), f"Fire: {s['fire'][:14]}", fill="white")
                    d.text((0, 36), f"WiFi: {s['wifi'][:14]}", fill="white")
                    d.text((0, 50), s["last_scan"][:21], fill="white")
            except OSError: pass
        time.sleep(0.4)

def shutdown(*_):
    stop.set(); time.sleep(0.5)
    for p in (hw.PIN_BUZZER, hw.PIN_LAMP, hw.PIN_LED_RED, hw.PIN_LED_GREEN): hw.set_out(p, False)
    GPIO.cleanup(); sys.exit(0)

if __name__ == "__main__":
    db.init(); hw.setup_gpio()
    signal.signal(signal.SIGTERM, shutdown); signal.signal(signal.SIGINT, shutdown)
    log.info("Warming up PIR/MQ-2 for 60 s..."); time.sleep(60)
    for fn in (rfid_loop, sensor_loop, wifi_loop):
        threading.Thread(target=fn, daemon=True).start()
    ui_loop()