import sqlite3
DB_PATH = "/home/pi/smartclass/classroom.db"

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS classes(class_id TEXT PRIMARY KEY, name TEXT, room TEXT, schedule TEXT);
CREATE TABLE IF NOT EXISTS students(student_id TEXT PRIMARY KEY, name TEXT NOT NULL,
  class_id TEXT REFERENCES classes(class_id), status TEXT DEFAULT 'active',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS rfid_cards(rfid_uid TEXT PRIMARY KEY,
  student_id TEXT NOT NULL REFERENCES students(student_id), status TEXT DEFAULT 'active',
  issued_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS devices(device_id TEXT PRIMARY KEY, device_label TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS student_device_map(mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id TEXT REFERENCES students(student_id), device_id TEXT REFERENCES devices(device_id),
  valid_from TEXT, valid_to TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS attendance(attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id TEXT NOT NULL REFERENCES students(student_id),
  class_id TEXT NOT NULL REFERENCES classes(class_id),
  date TEXT NOT NULL, time TEXT NOT NULL, status TEXT DEFAULT 'present',
  UNIQUE(student_id, class_id, date));
CREATE TABLE IF NOT EXISTS sensor_readings(reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT, temperature REAL, humidity REAL, smoke REAL, flame REAL, flame_do INTEGER,
  air_quality REAL, sound REAL, dark INTEGER, motion INTEGER, label TEXT);
CREATE TABLE IF NOT EXISTS wifi_metrics(metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT, packet_rate REAL, retry_rate REAL, rssi REAL, mgmt_rate REAL,
  channel_utilization REAL);
CREATE TABLE IF NOT EXISTS ml_predictions(prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
  model_type TEXT, model_version TEXT, timestamp TEXT, label TEXT, score REAL, latency_ms REAL);
CREATE TABLE IF NOT EXISTS network_activity(activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT, aggregate_key TEXT, domain TEXT, category TEXT, request_count INTEGER);
CREATE TABLE IF NOT EXISTS alerts(alert_id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT,
  severity TEXT, timestamp TEXT, message TEXT, source TEXT, status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS audit_logs(log_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT,
  action TEXT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, target TEXT, result TEXT);
"""

def connect():
    con = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def init():
    con = connect(); con.executescript(SCHEMA); con.commit(); con.close()

if __name__ == "__main__":
    init(); print("Database ready:", DB_PATH)