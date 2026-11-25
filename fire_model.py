import json, os, time
import numpy as np

LABELS = ["NORMAL", "SMOKE_HEAT_ANOMALY", "HIGH_FIRE_RISK"]
FEATURES = ["temperature", "humidity", "mq_v", "flame_v", "flame_do", "temp_rate"]
MODEL_DIR = "/home/pi/smartclass/models"

class FireModel:
    def __init__(self):
        self.kind, self.version = "rules", "rules-1.0"
        self.mean = np.zeros(len(FEATURES), np.float32)
        self.std = np.ones(len(FEATURES), np.float32)
        norm = os.path.join(MODEL_DIR, "fire_norm.json")
        if os.path.exists(norm):
            j = json.load(open(norm))
            self.mean = np.array(j["mean"], np.float32); self.std = np.array(j["std"], np.float32)
            self.version = j.get("version", "v1")
        tfl = os.path.join(MODEL_DIR, "fire_model.tflite")
        npz = os.path.join(MODEL_DIR, "fire_mlp.npz")
        Interpreter = None
        try:
            from tflite_runtime.interpreter import Interpreter
        except ImportError:
            try:
                from ai_edge_litert.interpreter import Interpreter
            except ImportError:
                pass
        if Interpreter and os.path.exists(tfl):
            self.it = Interpreter(model_path=tfl); self.it.allocate_tensors()
            self.inp = self.it.get_input_details()[0]["index"]
            self.out = self.it.get_output_details()[0]["index"]
            self.kind = "tflite"
        elif os.path.exists(npz):
            w = np.load(npz); self.W = [w[k] for k in sorted(w.files)]
            self.kind = "numpy-mlp"

    def predict(self, f):
        """f: dict with FEATURES. Returns (label, score, latency_ms)."""
        t0 = time.perf_counter()
        if self.kind == "rules":
            label, score = self._rules(f)
        else:
            x = (np.array([[f[k] for k in FEATURES]], np.float32) - self.mean) / self.std
            if self.kind == "tflite":
                self.it.set_tensor(self.inp, x); self.it.invoke()
                p = self.it.get_tensor(self.out)[0]
            else:   # W = [W1,b1,W2,b2,W3,b3] saved as a0..a5
                h = np.maximum(0, x @ self.W[0] + self.W[1])
                h = np.maximum(0, h @ self.W[2] + self.W[3])
                z = h @ self.W[4] + self.W[5]; p = np.exp(z - z.max()); p = (p / p.sum())[0]
            i = int(np.argmax(p)); label, score = LABELS[i], float(p[i])
        return label, score, (time.perf_counter() - t0) * 1000

    @staticmethod
    def _rules(f):
        # Fallback used until a trained model is deployed. Tune with your own baseline!
        smoke = f["mq_v"] > 2.0
        hot = f["temperature"] > 45 or f["temp_rate"] > 2.0     # deg C per minute
        flame = f["flame_do"] == 1
        if flame and (smoke or hot): return "HIGH_FIRE_RISK", 0.9
        if flame or smoke or hot:     return "SMOKE_HEAT_ANOMALY", 0.7
        return "NORMAL", 0.9