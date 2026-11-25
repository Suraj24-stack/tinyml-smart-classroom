import os, datetime
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import db

API_KEY = os.environ.get("SMARTCLASS_API_KEY", "change-me")   # never hard-code in production
app = FastAPI(title="Smart Classroom API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["GET"],
                   allow_headers=["*"])

def auth(x_api_key: str = Header(...)):
    if x_api_key != API_KEY: raise HTTPException(401, "Unauthorized")   # NFR-008

def q(sql, args=(), one=False):
    con = db.connect(); rows = [dict(r) for r in con.execute(sql, args).fetchall()]; con.close()
    return (rows[0] if rows else None) if one else rows

def latest_pred(kind):
    return q("SELECT label,score,model_version,timestamp FROM ml_predictions WHERE model_type=?"
             " ORDER BY prediction_id DESC LIMIT 1", (kind,), one=True)

@app.get("/api/dashboard", dependencies=[Depends(auth)])
def dashboard():
    today = datetime.date.today().isoformat()
    return {"attendance_count": q("SELECT COUNT(*) n FROM attendance WHERE date=?", (today,), True)["n"],
            "sensors": q("SELECT * FROM sensor_readings ORDER BY reading_id DESC LIMIT 1", one=True),
            "fire": latest_pred("fire"), "wifi": latest_pred("wifi"),
            "active_alerts": q("SELECT * FROM alerts WHERE status='active' ORDER BY alert_id DESC LIMIT 10")}

@app.get("/api/attendance", dependencies=[Depends(auth)])
def attendance(date: str = None):
    date = date or datetime.date.today().isoformat()
    return q("""SELECT a.*, s.name FROM attendance a JOIN students s USING(student_id)
                WHERE a.date=? ORDER BY a.time""", (date,))

@app.get("/api/sensors/latest", dependencies=[Depends(auth)])
def sensors(): return q("SELECT * FROM sensor_readings ORDER BY reading_id DESC LIMIT 1", one=True)

@app.get("/api/fire/status", dependencies=[Depends(auth)])
def fire(): return latest_pred("fire")

@app.get("/api/wifi/status", dependencies=[Depends(auth)])
def wifi(): return {"prediction": latest_pred("wifi"),
                    "metrics": q("SELECT * FROM wifi_metrics ORDER BY metric_id DESC LIMIT 1", one=True)}

@app.get("/api/alerts", dependencies=[Depends(auth)])
def alerts(limit: int = 50): return q("SELECT * FROM alerts ORDER BY alert_id DESC LIMIT ?", (min(limit, 500),))