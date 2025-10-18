# 必要なモジュールのインポート
import os, sqlite3, hashlib, time, logging, requests
# 外部モジュールからの関数インポート（イベント情報の解析とHTML取得）
from parsers import parse_events_generic
from scraper_login import fetch_events_html

# --- 環境変数から設定値の読み込み ---

# LINE Channel Access Token (メッセージ送信に必要)
TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
# メッセージを送信するLINEのターゲットIDリスト (カンマ区切り文字列をリストに変換)
TARGET_IDS = [s.strip() for s in os.getenv("TARGET_IDS","").split(",") if s.strip()]
# 既読管理用のSQLiteデータベースファイルのパス
DB_PATH = os.getenv("DB_PATH","seen.db")
# 一度に通知する最大イベント数
MAX_POSTS = int(os.getenv("MAX_POSTS","10"))

# ロギング設定 (INFOレベル以上のメッセージを、タイムスタンプ付きのフォーマットで出力)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# --- データベース関連の関数 ---

# データベースの初期化と接続を確立する関数
def ensure_db():
    # データベースファイルに接続 (ファイルが存在しない場合は作成される)
    conn = sqlite3.connect(DB_PATH)
    # 'seen' テーブルが存在しない場合、作成する
    # id: イベントのユニークID (PRIMARY KEY)、created_at: 登録日時
    conn.execute("""CREATE TABLE IF NOT EXISTS seen(
        id TEXT PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    # 変更を確定
    conn.commit(); 
    # 接続オブジェクトを返す
    return conn

# イベント情報からユニークID (UID) を生成する関数
def uid_from_event(e):
    # タイトル、日付、リンクを結合した文字列を基にする
    basis = f"{e.get('title','')}|{e.get('date','')}|{e.get('link','')}"
    # SHA-256でハッシュ値を計算し、それをUIDとする
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()

# 取得したイベントリストから、まだ通知していない新しいイベントのみをフィルタリングする関数
def filter_new(conn, events):
    cur = conn.cursor(); out=[]
    for e in events:
        # イベントからUIDを生成
        uid = uid_from_event(e)
        # データベースを検索し、このUIDが 'seen' テーブルに存在するか確認
        if cur.execute("SELECT 1 FROM seen WHERE id=?", (uid,)).fetchone():
            # 既に存在する場合（既読）はスキップ
            continue
        # 存在しない場合（新着）は、イベントデータにUIDを追加し、結果リストに追加
        e["_uid"] = uid; out.append(e)
    return out

# 新しく通知したイベントをデータベースに「既読」として登録する関数
def mark_seen(conn, events):
    cur = conn.cursor()
    for e in events:
        # UIDを 'seen' テーブルに挿入 (既に存在する場合は無視する: IGNORE)
        cur.execute("INSERT OR IGNORE INTO seen(id) VALUES(?)", (e["_uid"],))
    # 変更を確定
    conn.commit()

# --- LINE通知関連の関数 ---

# LINE Push Message APIを使ってメッセージを送信する関数
def push_message(to_id, text):
    url = "https://api.line.me/v2/bot/message/push"
    # 認証ヘッダーとコンテンツタイプを設定
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type":"application/json"}
    # 送信先のIDとメッセージの内容 (テキスト) を設定
    # LINEのメッセージ最大文字数に合わせ、テキストを最大4900文字に制限
    body = {"to": to_id, "messages":[{"type":"text","text":text[:4900]}]}
    # APIにPOSTリクエストを送信 (20秒のタイムアウトを設定)
    r = requests.post(url, headers=headers, json=body, timeout=20)
    # ステータスコードがエラーを示す場合 (4xx, 5xx) は例外を発生させる
    r.raise_for_status()

# イベント情報辞書をLINEメッセージとして整形する関数
def format_event(e):
    # タイトルをメインとし、日付とリンクがあれば追加する
    lines = [f"【学舎イベント新着】{e['title']}"]
    if e.get("date"): lines.append(f"日付: {e['date']}")
    if e.get("link"): lines.append(e['link'])
    # 各行を改行で結合して単一の文字列を返す
    return "\n".join(lines)

# --- メイン処理 ---

def main():
    # 環境変数 (TOKENとTARGET_IDS) が設定されているかチェック
    if not (TOKEN and TARGET_IDS):
        raise SystemExit("環境変数 LINE_CHANNEL_ACCESS_TOKEN / TARGET_IDS が未設定です。")
    
    # 1. イベント情報を含むHTMLを取得
    html, final_url = fetch_events_html()
    
    # 2. 取得したHTMLからイベント情報を解析し、イベントリストを取得
    events = parse_events_generic(html, final_url)
    
    # イベントが一つも見つからなかった場合の処理
    if not events:
        logging.warning("イベントが見つかりません。parsers.py のセレクタ調整が必要です。")
        return
    
    # 3. データベースへの接続を確立
    conn = ensure_db()
    
    # 4. 取得したイベントリストから、データベースに未登録の「新着」イベントを抽出
    new_events = filter_new(conn, events)
    
    # 新着イベントがなかった場合の処理
    if not new_events:
        logging.info("新着なし"); return
    
    # 5. 通知するイベントを MAX_POSTS 件までに制限
    new_events = new_events[:MAX_POSTS]
    
    # 6. 新着イベントをまとめて1つのメッセージに整形
    message = "\n\n".join(format_event(e) for e in new_events)
    
    # 7. ターゲットIDリストの各ユーザー/グループにメッセージを送信
    for tid in TARGET_IDS:
        push_message(tid, message); 
        # APIレート制限などを考慮し、送信間に1秒待機
        time.sleep(1.0)
        
    # 8. 通知したイベントをデータベースに既読として登録
    mark_seen(conn, new_events)
    
    # 9. 処理結果をロギング
    logging.info(f"送信完了: {len(new_events)}件")

# スクリプトが直接実行された場合に main 関数を呼び出す
if __name__ == "__main__":
    main()