# 必要なモジュールのインポート
import os, sqlite3, hashlib, time, logging, requests, sys

# ★ 追加: .env.dev を任意読み込み（あれば）
try:
    from dotenv import load_dotenv
    load_dotenv(".env.dev")
except Exception:
    pass

# ロギング設定 (先に初期化)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s: %(message)s"
)
logging.info("--- 起動 ---")

# 外部モジュールからの関数インポート（イベント情報の解析とHTML取得）
from parsers import parse_events_generic
from scraper_login import fetch_events_html

# --- 環境変数から設定値の読み込み ---
print("--- 環境変数からの設定値読み込み開始 ---")
# LINE Channel Access Token (メッセージ送信に必要)
TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
TARGET_IDS = [s.strip() for s in os.getenv("TARGET_IDS", "").split(",") if s.strip()]
DB_PATH = os.getenv("DB_PATH", "seen.db")
MAX_POSTS = int(os.getenv("MAX_POSTS", "10"))
# ★ 実行モードフラグ
IS_DRY = os.getenv("DRY_RUN", "false").lower() == "true"
USE_FIXTURE = bool(os.getenv("HTML_FIXTURE"))
VALIDATE_ONLY = os.getenv("VALIDATE_ONLY", "false").lower() == "true"

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
        if date:
            lines.append(f"日付: {date}")
        if link:
            lines.append(link)
        return "\n".join(lines)

    if FORMAT_STYLE == "compact":
        parts = [title]
        if date:
            parts.append(f"({date})")
        if link:
            parts.append(link)
        return " ".join(parts)

    # 既定: 箇条書き
    body = f"{BULLET}{title}"
    if date:
        body += f"\n  └ 日付: {date}"
    if link:
        body += f"\n  └ {link}"
    return body


def render_message(events):
    from datetime import datetime
    today = datetime.now().strftime("%m/%d時点")

    lines = []
    lines.append(f"🎓 しがくイベント 新着（{today}）")

    for e in events:
        title = e.get("title", "")
        date = e.get("date", "")
        link = e.get("link", "")

        lines.append(f"● {title}")
        if date:
            lines.append(f"└ 日付: {date}")
        if link:
            lines.append(f"└ {link}")
        lines.append("")  # 空行で区切り

    return "\n".join(lines).strip()
# ---------- Bさん: 通知整形ここまで ----------


# --- データベース関連の関数 ---
def ensure_db():
    logging.info(f"データベース接続/初期化開始: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS seen(
        id TEXT PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    conn.commit()
    logging.info("データベース 'seen' テーブルの存在確認/作成完了")
    return conn


def uid_from_event(e):
    basis = f"{e.get('title','')}|{e.get('date','')}|{e.get('link','')}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def filter_new(conn, events):
    print(f"新着イベントのフィルタリング開始: 全{len(events)}件")
    cur = conn.cursor()
    out = []
    for e in events:
        uid = uid_from_event(e)
        if cur.execute("SELECT 1 FROM seen WHERE id=?", (uid,)).fetchone():
            continue
        e["_uid"] = uid
        out.append(e)
    print(f"新着イベントのフィルタリング完了: {len(out)}件抽出されました")
    return out


def mark_seen(conn, events):
    print(f"既読としてマークするイベント数: {len(events)}件")
    cur = conn.cursor()
    for e in events:
        cur.execute("INSERT OR IGNORE INTO seen(id) VALUES(?)", (e["_uid"],))
    conn.commit()
    print("既読イベントのデータベース登録完了 (コミット済み)")


# --- LINE通知関連の関数 ---
def push_message(to_id, text):
    """特定の1ユーザーに push する"""
    # ★ 追加: DRY_RUN のときは送信せずプレビュー出力
    if IS_DRY:
        logging.info(f"[DRY_RUN] to={to_id}\n---\n{text}\n---")
        try:
            with open(os.getenv("GITHUB_STEP_SUMMARY", ""), "a", encoding="utf-8") as f:
                f.write("## 通知メッセージ プレビュー\n\n")
                f.write("```\n" + text + "\n```\n")
        except Exception:
            pass
        return

    # ★ 検証モード（validate API）
    if VALIDATE_ONLY:
        url = "https://api.line.me/v2/bot/message/validate/push"
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        body = {
            "to": (to_id or "U_dummy"),
            "messages": [{"type": "text", "text": text[:4900]}],
        }
        r = requests.post(url, headers=headers, json=body, timeout=20)
        logging.info(f"LINE validate API応答ステータス: {r.status_code}")
        logging.info(f"LINE validate API応答ボディ: {r.text}")
        r.raise_for_status()
        return

    # ★ 本番 push
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    body = {"to": to_id, "messages": [{"type": "text", "text": text[:4900]}]}
    r = requests.post(url, headers=headers, json=body, timeout=20)
    logging.info(f"LINE API応答ステータス: {r.status_code}")
    logging.info(f"LINE API応答ボディ: {r.text}")
    r.raise_for_status()
    print(f"LINEメッセージ送信成功 (To: {to_id})")


# ★ 追加: broadcast（一斉送信）用
def broadcast_message(text: str):
    """友だち全員に一斉送信する."""
    if IS_DRY:
        logging.info(f"[DRY_RUN:broadcast]\n---\n{text}\n---")
        try:
            with open(os.getenv("GITHUB_STEP_SUMMARY", ""), "a", encoding="utf-8") as f:
                f.write("## 通知メッセージ プレビュー（broadcast）\n\n")
                f.write("```\n" + text + "\n```\n")
        except Exception:
            pass
        return

    if VALIDATE_ONLY:
        # broadcast の検証API
        url = "https://api.line.me/v2/bot/message/validate/broadcast"
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        body = {"messages": [{"type": "text", "text": text[:4900]}]}
        r = requests.post(url, headers=headers, json=body, timeout=20)
        logging.info(f"LINE validate(broadcast) ステータス: {r.status_code}")
        logging.info(f"LINE validate(broadcast) ボディ: {r.text}")
        r.raise_for_status()
        return

    # 本番 broadcast
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    body = {"messages": [{"type": "text", "text": text[:4900]}]}
    r = requests.post(url, headers=headers, json=body, timeout=20)
    logging.info(f"LINE broadcast ステータス: {r.status_code}")
    logging.info(f"LINE broadcast ボディ: {r.text}")
    r.raise_for_status()
    print("LINEメッセージ broadcast 送信成功（友だち全員）")


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
    if USE_BROADCAST:
        if not TOKEN:
            raise SystemExit("環境変数 LINE_CHANNEL_ACCESS_TOKEN が未設定です。")
        logging.info("本番: broadcastモード（友だち全員）")
    else:
        if not (TOKEN and TARGET_IDS):
            raise SystemExit("環境変数 LINE_CHANNEL_ACCESS_TOKEN / TARGET_IDS が未設定です。")
        logging.info("本番: pushモード（TARGET_IDS宛て）")


# ★ B専用デバッグ関連のフラグ
USE_BROADCAST = os.getenv("USE_BROADCAST", "true").lower() == "true"  # デフォルトで broadcast
USE_B_SAMPLE = os.getenv("B_FORMAT_SAMPLE", "false").lower() == "true"    # サンプルで整形/送信する
SEND_B_SAMPLE = os.getenv("B_SEND_SAMPLE", "false").lower() == "true"     # 実際に送るか？（DRY_RUNに従う）

B_SAMPLE_EVENTS = [
    {"title": "帯試験申込開始", "date": "2025/11/07（日）10:00", "link": "https://example.com/123"},
    {"title": "しがくセミナー（東京）", "date": "2025/11/10（月）19:30", "link": "https://example.com/124"},
    {"title": "冬期講習受付スタート", "date": "2025/11/20（水）", "link": "https://example.com/125"},
]

if USE_B_SAMPLE and not SEND_B_SAMPLE:
    # 整形プレビューだけ（従来と同じ）
    logging.info("=== Bデバッグモード: 仮イベント（プレビューのみ・送信しない） ===")
    message = render_message(B_SAMPLE_EVENTS)
    print("\n===== 整形プレビュー =====\n")
    print(message)
    print("\n===== ↑この内容がLINE本文になります（DRY_RUN無関係）=====\n")
    raise SystemExit(0)


# --- メイン処理 ---
def main():
    print("=== スクリプト処理開始 ===")

    # 実行モードに応じたENVチェック
    _require_runtime_env()

    # 1. イベント情報を含むHTMLを取得
    print("1. HTMLコンテンツの取得開始...")
    html, final_url = fetch_events_html()
    print(f"1. HTMLコンテンツの取得完了。最終URL: {final_url}")

    # 2. 取得したHTMLからイベント情報を解析し、イベントリストを取得
    print("2. 取得したHTMLからのイベント情報解析開始...")
    events = parse_events_generic(html, final_url)
    print(f"2. イベント情報解析完了。見つかったイベント数: {len(events)}件")

    # イベントが一つも見つからなかった場合の処理
    if not events:
        print("イベントが見つかりません。parsers.py のセレクタ調整が必要です。")
        print("=== スクリプト処理終了 (警告あり) ===")
        return

    # 3. データベースへの接続を確立
    print("3. データベース接続確立処理へ...")
    conn = ensure_db()

    # 4. 取得したイベントリストから、データベースに未登録の「新着」イベントを抽出
    print("4. 新着イベントのフィルタリング処理へ...")
    new_events = filter_new(conn, events)

    if not new_events:
        print("新着イベントなし。通知スキップ。")
        print("=== スクリプト処理終了 (新着なし) ===")
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
    if USE_BROADCAST:
        logging.info("7. LINEメッセージ送信/プレビュー開始（broadcast＝友だち全員）")
        try:
            broadcast_message(message)
            logging.info("broadcast 送信/検証/プレビュー 完了")
        except requests.exceptions.HTTPError as e:
            logging.error(f"LINE broadcast 送信失敗: {e}")
    else:
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
