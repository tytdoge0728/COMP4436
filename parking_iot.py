
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
READ_FEED = ("https://api.thingspeak.com/channels/2921519/fields/1.json"
             "?api_key=4CGMVJSOWHCFOZ3J&results={limit}")
DB_PATH = os.path.abspath("parking.db")
print(f"[debug] Using DB file at: {DB_PATH}")
DB_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(DB_URL)



# ---------- DB SET‑UP -------------------------------------------------------



# ---------- HELPERS ---------------------------------------------------------
def fetch_all_history(limit=8000):
    url = f"https://api.thingspeak.com/channels/2921519/feeds.json?api_key=4CGMVJSOWHCFOZ3J&{limit}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    feeds = r.json()["feeds"]

    df = pd.DataFrame(feeds)

    # Select only created_at and all 8 fields
    field_cols = ["field" + str(i) for i in range(1, 9)]
    all_cols = ["entry_id", "created_at"] + field_cols
    df = df[all_cols].copy()

    df.rename(columns={"created_at": "ts_utc"}, inplace=True)
    df.dropna(inplace=True)  # optional: remove rows with any NaN

    # Convert types
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
        df[f] = df[f].astype(int)

    df["occupied"] = df[field_cols].sum(axis=1)
    df["ts_utc"] = df["ts_utc"].astype(str)

    # Remove duplicates already in DB
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
    # Drop and recreate the table
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS readings;")
        conn.exec_driver_sql("""
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
        """)

    # Then load historical data
    df = fetch_all_history()
    if df.empty:
        print("[info] No data fetched.")
        return

    print(f"[info] Fetched {len(df)} historical records.")
    persist(df)
    print("[success] Initial historical data saved.")


def collect_once(limit=max):
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
    # Print full DB path for sanity check


    # Read everything first
    df = pd.read_sql("SELECT ts_utc, occupied FROM readings", engine)


    # Convert to datetime and filter in pandas
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    since = now - dt.timedelta(days=days)


    df = df[df["ts_utc"] >= since]
    df.set_index("ts_utc", inplace=True)


    return df



def analyze(days):
    df = load_data(days)
    if df.empty:
        print("No data yet – run the collector first.")
        return

    # Daily average occupancy
    daily = (df["occupied"].resample("1D").mean() / 8) * 100


    # Peak usage hour per day (handle missing data gracefully)
    hourly = (df["occupied"].resample("1h").mean() / 8)

    peak_hours = (
        hourly.groupby(hourly.index.date)
              .agg(lambda s: s.dropna().idxmax().hour if not s.dropna().empty else None)
    )

    print("\nDaily Utilisation (% occupied)")
    print(daily.tail().round(1).to_string(header=False))

    print("\nPeak Hour (local clock)")
    print(peak_hours.tail().to_string(header=False))

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

    print("╔══════════════════════════════════════════════╗")
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


# ---------- CLI -------------------------------------------------------------
def cli():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("init")
    g = sub.add_parser("collect"); g.add_argument("--interval", type=int, default=30)
    g = sub.add_parser("analyze"); g.add_argument("--days", type=int, default=7)
    g = sub.add_parser("recommend"); g.add_argument("--days", type=int, default=14)

    args = p.parse_args()
    if args.cmd == "collect":    run_collector(args.interval)
    elif args.cmd == "analyze":  analyze(args.days)
    elif args.cmd == "recommend":recommend(args.days)
    elif args.cmd == "init":init_from_history()




if __name__ == "__main__":
    cli()
