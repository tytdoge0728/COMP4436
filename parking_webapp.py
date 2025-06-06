# parking_webapp.py — Flask web interface for IoT Parking‑Space Monitor
# ----------------------------------------------------------------------
# Prerequisites (create and activate a venv first):
#   pip install flask pandas sqlalchemy schedule requests
# ----------------------------------------------------------------------
# Project layout (same folder):
#   parking_iot.py      ← your existing CLI/analytics module (unchanged)
#   parking_webapp.py   ← this file – run it to launch the web UI
# ----------------------------------------------------------------------
# Usage:
#   python parking_webapp.py   # starts local web‑server at http://localhost:8000
# ----------------------------------------------------------------------

import threading, time
from typing import List, Dict

from flask import Flask, jsonify, render_template_string, request
import parking_iot                                   # ← import your module
from flask_socketio import SocketIO
from flask import render_template  # Ensure render_template is imported

# ---------------------------- configuration --------------------------------
COLLECT_INTERVAL = 30   # seconds between background polls to ThingSpeak
PORT              = 8000

# ----------------------- background data collector -------------------------
_collector_thread: threading.Thread | None = None
_collector_running: bool = False


def _collector_loop(interval: int) -> None:
    """Continuously pull the latest readings and persist them."""
    global _collector_running
    _collector_running = True
    while _collector_running:
        try:
            socketio.emit('syncing')  # Notify clients that syncing has started
            parking_iot.collect_once(limit=100)  # Fetch and persist the latest data
            latest = latest_status()
            socketio.emit('update_status', latest)  # Emit the latest status to connected clients
            socketio.emit('sync_complete')  # Notify clients that syncing is complete
        except Exception as exc:
            print("[collector] error:", exc)
        time.sleep(interval)


def _start_collector_thread(interval: int = COLLECT_INTERVAL) -> None:
    """Start the background collector exactly once."""
    global _collector_thread
    if (_collector_thread is None):
        _collector_thread = threading.Thread(target=_collector_loop, args=(interval,), daemon=True)
        _collector_thread.start()
        print(f"[collector] running every {interval}s …")


# ------------------------------- Flask app ---------------------------------
app = Flask(__name__)
socketio = SocketIO(app)

# ――― compatibility shim: Flask <3 had before_first_request; Flask ≥3 removed it ―――
if hasattr(app, "before_first_request"):

    @app.before_first_request  # type: ignore[attr-defined]
    def _on_first_request():
        _start_collector_thread()

else:
    # Flask 3.x path: start immediately at import time
    _start_collector_thread()


# ---------- helper wrappers around functions in parking_iot.py -------------

def latest_status() -> Dict:
    df = parking_iot.load_data(days=1)
    if df.empty:
        return {}
    latest = df.tail(1)
    ts = latest.index[-1].isoformat()
    occupied = int(latest["occupied"].iloc[0])
    return {
        "timestamp": ts,
        "occupied": occupied,
        "available": 8 - occupied,
    }


# ----------------------------- JSON endpoints ------------------------------

@app.get("/api/status")
def api_status():
    df = parking_iot.load_data(days=1)
    if df.empty:
        # Return default structure with all slots available
        return jsonify({
            "timestamp": None,
            "occupied": 0,
            "available": 8,
            "fields": [{"slot": i, "status": 0} for i in range(1, 9)]  # Default: all slots available
        })

    latest = df.tail(1)  # Get the latest row
    print("DEBUG: Latest row from database:\n", latest)  # Debugging: Print the latest row

    ts = latest.index[-1].isoformat()

    # Map field1–field8 to slots and calculate statuses
    field_states = []
    occupied_count = 0

    for i in range(1, 9):  # Iterate over slots 1 to 8
        col = f"field{i}"
        if col in latest.columns:
            status = int(latest[col].iloc[0])  # Get the status for the slot
        else:
            print(f"DEBUG: Column {col} not found in latest row.")  # Debugging: Missing column
            status = 0  # Default to 0 (available) if the column doesn't exist
        field_states.append({"slot": i, "status": status})
        occupied_count += status

    print("DEBUG: fields =", field_states)  # Debugging: Print the fields array

    return jsonify({
        "timestamp": ts,
        "occupied": occupied_count,
        "available": 8 - occupied_count,
        "fields": field_states
    })


@app.get("/api/analyze")
def api_analyze():
    days = int(request.args.get("days", 7))
    df = parking_iot.load_data(days)
    if df.empty:
        return jsonify({"error": "no data"}), 404

    daily = (df["occupied"].resample("1D").mean() / 8 * 100).round(1)
    trend = parking_iot.describe_trend(daily)  # use original datetime index

    daily.index = daily.index.astype(str)  # convert AFTER trend analysis
    return jsonify({"daily": daily.to_dict(), "trend": trend})




@app.get("/api/history")
def api_history():
    days = int(request.args.get("days", 30))
    df = parking_iot.load_data(days)
    if df.empty:
        return jsonify({"error": "no data"}), 404
    df["weekday"] = df.index.weekday
    df["hour"] = df.index.hour
    weekday_avg = (df.groupby("weekday")["occupied"].mean() / 8 * 100).round(1)
    weekday_avg.index = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hour_avg = (df.groupby("hour")["occupied"].mean() / 8 * 100).round(1)
    return jsonify({"weekday": weekday_avg.to_dict(), "hourly": hour_avg.to_dict()})


@app.get("/api/recommend")
def api_recommend():
    days = int(request.args.get("days", 14))
    df = parking_iot.load_data(days)
    if df.empty:
        return jsonify({"error": "no data"}), 404
    hourly = df.resample("1h").mean()["occupied"]
    high, low = 0.8, 0.3
    peak_hours = hourly[hourly > high].index.hour
    trough_hours = hourly[hourly < low].index.hour
    peak = peak_hours.value_counts().idxmax() if not peak_hours.empty else None
    trough = trough_hours.value_counts().idxmax() if not trough_hours.empty else None
    tips: List[str] = []
    if peak is not None:
        tips.append(
            f"Premium pricing between {peak:02d}:00–{peak + 1:02d}:00 (≥ {int(high * 100)}% full)"
        )
    if trough is not None:
        tips.append(
            f"Early‑bird discount around {trough:02d}:00–{trough + 1:02d}:00 (≤ {int(low * 100)}% full)"
        )
    if not tips:
        tips.append("No strong trends detected – keep flat pricing.")
    return jsonify({"tips": tips})




@app.route("/")
def index():
    return render_template("index.html")

# Add a WebSocket route for testing connectivity
@socketio.on('connect')
def handle_connect():
    """Send the latest status to the client when they connect."""
    print("[socketio] Client connected")
    try:
        latest = latest_status()
        socketio.emit('update_status', latest)  # Send the latest status to the client
        print("[socketio] Sent latest status to client on connect")
    except Exception as exc:
        print("[socketio] Error during data collection on connect:", exc)

# ------------------------------ entry point -------------------------------
if __name__ == "__main__":
    # Ensure we have baseline data (only the first time – comment out if DB already populated)
    parking_iot.init_from_history()
    socketio.run(app, host="0.0.0.0", port=PORT, debug=False)
