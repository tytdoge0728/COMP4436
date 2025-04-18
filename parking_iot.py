"""
IoT Parking‑Space Monitor / Analyzer
------------------------------------
USAGE:
  # ❶ run a live collector (polls every 30 s)
  python parking_iot.py collect --interval 30

  # ❷ on demand, study the last 7 days
  python parking_iot.py analyze --days 7

  # ❸ get dynamic‑pricing / reservation tips
  python parking_iot.py recommend --days 14
"""
import argparse, datetime as dt, json, os, sys, time
import pandas as pd, requests, schedule
from sqlalchemy import create_engine, text
from sqlalchemy.types import Text, Integer  

# ---------- CONFIG ----------------------------------------------------------
READ_FEED = ("https://api.thingspeak.com/channels/2924982/feeds.json?api_key=BEOW0KPMVA8I1OOV&results={limit}")
DB_PATH = os.path.abspath("parking.db")
print(f"[debug] Using DB file at: {DB_PATH}")
DB_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(DB_URL)

# ---------- HELPERS ---------------------------------------------------------
def reset_database():
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS readings;"))
        conn.execute(text("""
            CREATE TABLE readings (
                entry_id INTEGER PRIMARY KEY,
                ts_utc   TEXT    NOT NULL,
                field1   INTEGER,
                field2   INTEGER,
                field3   INTEGER,
                field4   INTEGER,
                field5   INTEGER,
                field6   INTEGER,
                field7   INTEGER,
                field8   INTEGER,
                occupied INTEGER NOT NULL
            );
        """))
        print("[info] Database table 'readings' reset.")

def fetch_all_history(limit=8000):
    url = f"https://api.thingspeak.com/channels/2924982/feeds.json?api_key=BEOW0KPMVA8I1OOV&results={limit}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    feeds = r.json()["feeds"]
    print(feeds)

    df = pd.DataFrame(feeds)

    field_cols = ["field" + str(i) for i in range(1, 9)]
    all_cols = ["entry_id", "created_at"] + field_cols
    df = df[all_cols].copy()

    df.rename(columns={"created_at": "ts_utc"}, inplace=True)
    df.dropna(inplace=True)

    df["entry_id"] = df["entry_id"].astype(int)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"])

    for f in field_cols:
        df[f] = df[f].astype(int)

    return df

def persist(df: pd.DataFrame) -> None:
    if df.empty:
        print("[debug] DataFrame is empty — skipping.")
        return

    df.columns = df.columns.str.strip()
    df["entry_id"] = df["entry_id"].astype(int)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"])

    field_cols = [f"field{i}" for i in range(1, 9)]
    for f in field_cols:
        if f not in df.columns:
            df[f] = 0  # Ensure missing fields are added with default value 0
        df[f] = df[f].astype(int)

    df["occupied"] = df[field_cols].sum(axis=1)
    df["ts_utc"] = df["ts_utc"].astype(str)

    existing = pd.read_sql("SELECT entry_id FROM readings", engine)
    existing_ids = set(existing["entry_id"])
    df = df[~df["entry_id"].isin(existing_ids)]

    if df.empty:
        print("[info] No new data to insert.")
        return

    df.to_sql(
        name="readings",
        con=engine,
        if_exists="append",
        index=False,
        method="multi",
        dtype={**{f: Integer() for f in field_cols},
               "entry_id": Integer(), "ts_utc": Text(), "occupied": Integer()}
    )
    print(f"[info] Persisted {len(df)} new records.")

def init_from_history():
    reset_database()
    df = fetch_all_history()
    if df.empty:
        print("[info] No data fetched.")
        return
    print(f"[info] Fetched {len(df)} historical records.")
    persist(df)
    print("[success] Initial historical data saved.")

def collect_once(limit=8000):
    df = fetch_all_history(limit)
    persist(df)

def run_collector(interval):
    schedule.every(interval).seconds.do(collect_once)
    print(f"[collector] polling ThingSpeak every {interval}s … Ctrl‑C to stop")
    while True:
        schedule.run_pending()
        time.sleep(1)

# ---------- ANALYTICS -------------------------------------------------------
def load_data(days):
    # Include field1 to field8 in the query
    query = """
        SELECT ts_utc, occupied, field1, field2, field3, field4, field5, field6, field7, field8
        FROM readings
    """
    df = pd.read_sql(query, engine)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    since = now - dt.timedelta(days=days)
    df = df[df["ts_utc"] >= since]
    df.set_index("ts_utc", inplace=True)
    return df

def describe_trend(daily: pd.Series):
    if daily.empty or daily.count() < 2:
        return "Not enough data to determine a trend."
    series = daily.dropna()
    x = range(len(series))
    y = series.values
    slope = pd.Series(y).diff().mean()
    if slope > 1:
        direction = "📈 Increasing"
    elif slope < -1:
        direction = "📉 Decreasing"
    else:
        direction = "🔁 Flat"
    peak_day = series.idxmax()
    peak_day_str = peak_day.strftime("%A")
    peak_comment = " (Peaks on weekend)" if peak_day_str in ["Saturday", "Sunday"] else " (Peaks on weekday)"
    return f"{direction}{peak_comment}"

def analyze(days):
    df = load_data(days)
    if df.empty:
        print("No data yet – run the collector first.")
        return
    print("[debug] Loaded entries date range:", df.index.min(), "to", df.index.max())
    print("[debug] Unique dates:", df.index.date)

    daily = (df["occupied"].resample("1D").mean() / 8) * 100
    hourly = (df["occupied"].resample("1h").mean() / 8)
    peak_hours = (
        hourly.groupby(hourly.index.date)
              .agg(lambda s: s.dropna().idxmax().hour if not s.dropna().empty else None)
    )

    print("\nDaily Utilisation (% occupied)")
    print(daily.round(1).to_string())  


    print("\nPeak Hour (local clock)")
    print(peak_hours.to_string(header=False))

    cutoff = daily.index.max() - pd.Timedelta(days=days)
    daily_last_n = daily[daily.index > cutoff]
    trend_desc = describe_trend(daily_last_n)
    print(f"\n[Trend Analysis] {trend_desc}")

def historical_analysis(days):
    df = load_data(days)
    if df.empty:
        print("No data yet – run the collector first.")
        return

    df["weekday"] = df.index.weekday  # 0 = Monday, 6 = Sunday
    df["hour"] = df.index.hour

    # Average occupancy by weekday
    weekday_avg = df.groupby("weekday")["occupied"].mean() / 8 * 100
    weekday_avg.index = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # Average occupancy by hour of the day
    hour_avg = df.groupby("hour")["occupied"].mean() / 8 * 100

    # Top peak periods
    peak_hours = hour_avg.sort_values(ascending=False).head(5)

    print("\n[📊 Historical Weekday Pattern (% occupancy)]")
    print(weekday_avg.round(1).to_string())

    print("\n[🕒 Average Occupancy by Hour (%)]")
    print(hour_avg.round(1).to_string())

    print("\n[🔥 Peak Usage Hours (All Time)]")
    for h, pct in peak_hours.items():
        print(f"{h:02d}:00 - {pct:.1f}%")



def recommend(days, high=0.8, low=0.3):
    df = load_data(days)
    if df.empty:
        print("No data yet – run the collector first.")
        return

    hourly = df.resample("1h").mean()
    utilisation = hourly["occupied"]

    peak_hours = utilisation[utilisation > high].index.hour
    trough_hours = utilisation[utilisation < low].index.hour

    peak = peak_hours.value_counts().idxmax() if not peak_hours.empty else None
    trough = trough_hours.value_counts().idxmax() if not trough_hours.empty else None

    print("╔═══════════════════════════════════════════════════╗")
    print("║ Dynamic‑Pricing / Reservation Suggestions    ║")
    print("╠══════════════════════════════════════════════╣")
    if peak is not None:
        print(f"║ ‣ Consider **premium pricing** between "
              f"{peak:02d}:00‑{peak+1:02d}:00 (≥ {high*100:.0f}% full) ║")
    if trough is not None:
        print(f"║ ‣ Offer **early‑bird discounts** around "
              f"{trough:02d}:00‑{trough+1:02d}:00 (≤ {low*100:.0f}% full) ║")
    if peak is None and trough is None:
        print("║ No strong usage trends detected for pricing tips. ║")
    print("╚══════════════════════════════════════════════╝")

# ---------- show status -------------------------------------------------------------

def show_latest_status():
    try:
        df = pd.read_sql("SELECT ts_utc, occupied FROM readings ORDER BY ts_utc DESC LIMIT 1", engine)
        if df.empty:
            print("[!] No data found.")
            return
        latest = df.iloc[0]
        timestamp = latest["ts_utc"]
        occupied = int(latest["occupied"])
        available = 8 - occupied
        print(f"[{timestamp}] Occupied: {occupied} | Available: {available}")
    except Exception as e:
        print(f"[Error] {e}")

# ---------- CLI -------------------------------------------------------------
def cli():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("init")
    g = sub.add_parser("collect"); g.add_argument("--interval", type=int, default=30)
    g = sub.add_parser("analyze"); g.add_argument("--days", type=int, default=7)
    g = sub.add_parser("recommend"); g.add_argument("--days", type=int, default=14)
    g = sub.add_parser("status")
    g = sub.add_parser("history");g.add_argument("--days", type=int, default=30)



    args = p.parse_args()
    if args.cmd == "collect":    run_collector(args.interval)
    elif args.cmd == "analyze":  analyze(args.days)
    elif args.cmd == "recommend":recommend(args.days)
    elif args.cmd == "init":init_from_history()
    elif args.cmd == "status":show_latest_status()
    elif args.cmd == "history": historical_analysis(args.days)


if __name__ == "__main__":
    cli()
