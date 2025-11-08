# 必要なモジュールのインポート
import os, sqlite3, hashlib, time, logging, requests, sys

# ★ 追加: .env.dev を任意読み込み（あれば）
try:
    from dotenv import load_dotenv
    load_dotenv(".env.dev")
except Exception:
    pass

# ロギング設定 (先に初期化)
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO").upper(), format="%(asctime)s %(levelname)s: %(message)s")
logging.info("--- 起動 ---")

# 外部モジュールからの関数インポート（イベント情報の解析とHTML取得）
from parsers import parse_events_generic
from scraper_login import fetch_events_html

# --- 環境変数から設定値の読み込み ---
TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
TARGET_IDS = [s.strip() for s in os.getenv("TARGET_IDS","").split(",") if s.strip()]
DB_PATH = os.getenv("DB_PATH","seen.db")
MAX_POSTS = int(os.getenv("MAX_POSTS","10"))

# ★ 追加: 実行モードフラグ
IS_DRY = os.getenv("DRY_RUN","false").lower() == "true"
USE_FIXTURE = bool(os.getenv("HTML_FIXTURE"))
VALIDATE_ONLY = os.getenv("VALIDATE_ONLY","false").lower() == "true"

# ---------- Bさん: 通知整形ここから ----------
# スタイル調整パラメータ（環境変数で上書き可）
FORMAT_STYLE   = os.getenv("FORMAT_STYLE", "list")   # "list" | "cards" | "compact"
HEADER_TITLE   = os.getenv("HEADER_TITLE", "🎓 学舎イベント 新着")
SEPARATOR      = os.getenv("SEPARATOR", "\n\n")      # 複数件の区切り
BULLET         = os.getenv("BULLET", "● ")
SHOW_HEADER    = os.getenv("SHOW_HEADER", "true").lower() == "true"

def format_event(e: dict) -> str:
    """1件のイベントをLINEメッセージ化"""
    title = e.get("title") or "(件名未取得)"
    date  = e.get("date")
    link  = e.get("link")

    if FORMAT_STYLE == "cards":
        lines = [f""]
        if date: lines.append(f"日付: {date}")
        if link: lines.append(link)
        return "\n".join(lines)

    if FORMAT_STYLE == "compact":
        parts = [title]
        if date: parts.append(f"({date})")
        if link: parts.append(link)
        return " ".join(parts)

    # 既定: 箇条書き
    body = f"{BULLET}{title}"
    if date: body += f"\n  └ 日付: {date}"
    if link: body += f"\n  └ {link}"
    return body

def render_message(events: list[dict]) -> str:
    parts = [format_event(e) for e in events]
    if SHOW_HEADER:
        return f"{HEADER_TITLE}\n{SEPARATOR.join(parts)}"
    return SEPARATOR.join(parts)
# ---------- Bさん: 通知整形ここまで ----------

# --- データベース関連の関数 ---
def ensure_db():
    logging.info(f"データベース接続/初期化開始: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS seen(
        id TEXT PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    logging.info("データベース 'seen' テーブルの存在確認/作成完了")
    return conn

def uid_from_event(e):
    basis = f"{e.get('title','')}|{e.get('date','')}|{e.get('link','')}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()

def filter_new(conn, events):
    logging.info(f"新着イベントのフィルタリング開始: 全{len(events)}件")
    cur = conn.cursor(); out=[]
    for e in events:
        uid = uid_from_event(e)
        if cur.execute("SELECT 1 FROM seen WHERE id=?", (uid,)).fetchone():
            continue
        e["_uid"] = uid; out.append(e)
    logging.info(f"新着イベントのフィルタリング完了: {len(out)}件抽出されました")
    return out

def mark_seen(conn, events):
    logging.info(f"既読としてマークするイベント数: {len(events)}件")
    cur = conn.cursor()
    for e in events:
        cur.execute("INSERT OR IGNORE INTO seen(id) VALUES(?)", (e["_uid"],))
    conn.commit()
    logging.info("既読イベントのデータベース登録完了 (コミット済み)")

# --- LINE通知関連の関数 ---
def push_message(to_id, text):
    # ★ 追加: DRY_RUN のときは送信せずプレビュー出力
    if IS_DRY:
        logging.info(f"[DRY_RUN] to={to_id}\n---\n{text}\n---")
        # Step Summary にも出す（Actions実行時の見やすさ向上）
        try:
            with open(os.getenv("GITHUB_STEP_SUMMARY",""), "a", encoding="utf-8") as f:
                f.write("## 通知メッセージ プレビュー\n\n")
                f.write("```\n" + text + "\n```\n")
        except Exception:
            pass
        return

    # ★ 検証モード（メッセージ検証APIを使う、※必要なら使用）
    if VALIDATE_ONLY:
        url = "https://api.line.me/v2/bot/message/validate/push"
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type":"application/json"}
        body = {"to": (to_id or "U_dummy"), "messages":[{"type":"text","text":text[:4900]}]}
        r = requests.post(url, headers=headers, json=body, timeout=20)
        logging.info(f"LINE validate API応答ステータス: {r.status_code}")
        r.raise_for_status()
        return

    # ★ 本番送信用（従来どおり）
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type":"application/json"}
    body = {"to": to_id, "messages":[{"type":"text","text":text[:4900]}]}
    r = requests.post(url, headers=headers, json=body, timeout=20)
    logging.info(f"LINE API応答ステータス: {r.status_code}")
    r.raise_for_status()
    logging.info(f"LINEメッセージ送信成功 (To: {to_id})")

# ★ 追加: 実行モードに応じた必須ENVチェック
def _require_runtime_env():
    if IS_DRY and USE_FIXTURE:
        # デバッグ（本文整形/パース確認）では何も要らない
        logging.info("デバッグ: DRY_RUN + HTML_FIXTURE → ENVチェックをスキップ")
        return
    if VALIDATE_ONLY:
        if not TOKEN:
            raise SystemExit("LINE_CHANNEL_ACCESS_TOKEN が未設定（VALIDATE_ONLY）")
        logging.info("VALIDATE_ONLY: TOKENのみ必須、TARGET_IDSはダミー可")
        return
    # 本番送信
    if not (TOKEN and TARGET_IDS):
        raise SystemExit("環境変数 LINE_CHANNEL_ACCESS_TOKEN / TARGET_IDS が未設定です。")

# --- メイン処理 ---
def main():
    logging.info("=== スクリプト処理開始 ===")
    _require_runtime_env()

    # 1. イベント情報を含むHTMLを取得（HTML_FIXTURE指定時はログイン不要）
    logging.info("1. HTMLコンテンツの取得開始...")
    html, final_url = fetch_events_html()
    logging.info(f"1. HTMLコンテンツの取得完了。最終URL: {final_url}")

    # 2. HTMLからイベント解析
    logging.info("2. 取得したHTMLからのイベント情報解析開始...")
    events = parse_events_generic(html, final_url)
    logging.info(f"2. イベント情報解析完了。見つかったイベント数: {len(events)}件")

    if not events:
        logging.warning("イベントが見つかりません。parsers.py のセレクタ調整が必要です。")
        logging.info("=== スクリプト処理終了 (警告あり) ===")
        return

    # 3. DB接続（DRYでも新着ロジックは見たいなら接続する）
    logging.info("3. データベース接続確立処理へ...")
    conn = ensure_db()

    # 4. 新着抽出
    logging.info("4. 新着イベントのフィルタリング処理へ...")
    new_events = filter_new(conn, events)

    if not new_events:
        logging.info("新着イベントなし。通知スキップ。")
        logging.info("=== スクリプト処理終了 (新着なし) ===")
        return

    logging.info(f"新着イベント数: {len(new_events)}件")

    # 5. 件数制限
    original_new_count = len(new_events)
    new_events = new_events[:MAX_POSTS]
    logging.info(f"5. 通知イベント数を {MAX_POSTS} 件に制限。実際に通知する件数: {len(new_events)}件")

    # 6. 整形
    logging.info("6. LINEメッセージへの整形開始...")
    message = render_message(new_events)
    logging.info(f"6. メッセージ整形完了。メッセージ全体の文字数: {len(message)}")

    # 7. 送信（DRYならプレビュー）
    logging.info(f"7. LINEメッセージ送信/プレビュー開始 (対象ID数: {len(TARGET_IDS) or 1})")
    target_ids = TARGET_IDS or ["U_dummy"]  # DRY/VALIDATE_ONLY 用のダミー
    for i, tid in enumerate(target_ids, 1):
        try:
            push_message(tid, message)
            logging.info(f"送信/検証/プレビュー 完了 {i}/{len(target_ids)} (ID: {tid})")
        except requests.exceptions.HTTPError as e:
            logging.error(f"LINEメッセージ送信失敗 {i}/{len(target_ids)} (ID: {tid}): {e}")
        time.sleep(1.0)  # API保護

    # 8. 既読マーク
    logging.info("8. 通知済みイベントの既読マーク処理へ...")
    mark_seen(conn, new_events)

    # 9. まとめ
    logging.info(f"9. 処理結果: 新規イベント {original_new_count}件中、{len(new_events)}件を送信/既読マーク。")
    logging.info("=== スクリプト処理正常終了 ===")

if __name__ == "__main__":
    main()
