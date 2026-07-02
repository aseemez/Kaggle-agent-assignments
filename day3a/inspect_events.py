import sqlite3, json

conn = sqlite3.connect("my_agent_data.db")
rows = conn.execute(
    "SELECT timestamp, event_data FROM events WHERE session_id='test-db-session-01' ORDER BY timestamp"
).fetchall()

for ts, data in rows:
    parsed = json.loads(data)
    print(f"--- {ts} ---")
    print(json.dumps(parsed, indent=2))
    print()