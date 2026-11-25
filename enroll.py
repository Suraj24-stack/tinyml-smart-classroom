import RPi.GPIO as GPIO, time, db, hw
from mfrc522 import MFRC522
db.init(); con = db.connect()
GPIO.setmode(GPIO.BCM); reader = MFRC522(pin_rst=hw.PIN_RC522_RST)

cls = input("Class ID (e.g. BCT-3A): ").strip()
con.execute("INSERT OR IGNORE INTO classes(class_id,name) VALUES(?,?)", (cls, cls))
while True:
    sid = input("Student ID (blank to quit): ").strip()
    if not sid: break
    name = input("Student name: ").strip()
    print("Tap the student's card...")
    uid = None
    while not uid:
        st, _ = reader.MFRC522_Request(reader.PICC_REQIDL)
        if st == reader.MI_OK:
            st, u = reader.MFRC522_Anticoll()
            if st == reader.MI_OK: uid = "".join(f"{b:02X}" for b in u[:4])
        time.sleep(0.1)
    try:
        con.execute("INSERT INTO students(student_id,name,class_id) VALUES(?,?,?)", (sid, name, cls))
        con.execute("INSERT INTO rfid_cards(rfid_uid,student_id) VALUES(?,?)", (uid, sid))
        con.execute("INSERT INTO audit_logs(user_id,action,target,result) VALUES('admin','enroll',?,'ok')", (sid,))
        con.commit(); print(f"Enrolled {name} -> {uid}")
    except Exception as e:
        con.rollback(); print("Error (duplicate ID or card?):", e)
    time.sleep(1)
GPIO.cleanup()