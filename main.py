import os, sqlite3, hashlib, time, logging, requests
from parsers import parse_events_generic
from scraper_login import fetch_events_html

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
TARGET_IDS = [s.strip() for s in os.getenv("TARGET_IDS","").split(",") if s.strip()]
DB_PATH = os.getenv("DB_PATH","seen.db")
MAX_POSTS = int(os.getenv("MAX_POSTS","10"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

def ensure_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS seen(
        id TEXT PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit(); return conn

def uid_from_event(e):
    basis = f"{e.get('title','')}|{e.get('date','')}|{e.get('link','')}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()

def filter_new(conn, events):
    cur = conn.cursor(); out=[]
    for e in events:
        uid = uid_from_event(e)
        if cur.execute("SELECT 1 FROM seen WHERE id=?", (uid,)).fetchone():
            continue
        e["_uid"] = uid; out.append(e)
    return out

def mark_seen(conn, events):
    cur = conn.cursor()
    for e in events:
        cur.execute("INSERT OR IGNORE INTO seen(id) VALUES(?)", (e["_uid"],))
    conn.commit()

def push_message(to_id, text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type":"application/json"}
    body = {"to": to_id, "messages":[{"type":"text","text":text[:4900]}]}
    r = requests.post(url, headers=headers, json=body, timeout=20)
    r.raise_for_status()

def format_event(e):
    lines = [f"【学舎イベント新着】{e['title']}"]
    if e.get("date"): lines.append(f"日付: {e['date']}")
    if e.get("link"): lines.append(e['link'])
    return "\n".join(lines)

def main():
    if not (TOKEN and TARGET_IDS):
        raise SystemExit("環境変数 LINE_CHANNEL_ACCESS_TOKEN / TARGET_IDS が未設定です。")
    html, final_url = fetch_events_html()
    events = parse_events_generic(html, final_url)
    if not events:
        logging.warning("イベントが見つかりません。parsers.py のセレクタ調整が必要です。")
        return
    conn = ensure_db()
    new_events = filter_new(conn, events)
    if not new_events:
        logging.info("新着なし"); return
    new_events = new_events[:MAX_POSTS]
    message = "\n\n".join(format_event(e) for e in new_events)  # 1通にまとめて送信
    for tid in TARGET_IDS:
        push_message(tid, message); time.sleep(1.0)
    mark_seen(conn, new_events)
    logging.info(f"送信完了: {len(new_events)}件")

if __name__ == "__main__":
    main()
