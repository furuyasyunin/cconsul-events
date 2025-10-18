# 必要なモジュールのインポート
import os, sqlite3, hashlib, time, logging, requests
# 外部モジュールからの関数インポート（イベント情報の解析とHTML取得）
from parsers import parse_events_generic
from scraper_login import fetch_events_html

# --- 環境変数から設定値の読み込み ---
logging.info("--- 環境変数からの設定値読み込み開始 ---")
# LINE Channel Access Token (メッセージ送信に必要)
TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
# メッセージを送信するLINEのターゲットIDリスト (カンマ区切り文字列をリストに変換)
TARGET_IDS = [s.strip() for s in os.getenv("TARGET_IDS","").split(",") if s.strip()]
# 既読管理用のSQLiteデータベースファイルのパス
DB_PATH = os.getenv("DB_PATH","seen.db")
# 一度に通知する最大イベント数
MAX_POSTS = int(os.getenv("MAX_POSTS","10"))
logging.info(f"DB_PATH: {DB_PATH}, MAX_POSTS: {MAX_POSTS}, TARGET_IDS数: {len(TARGET_IDS)}")
logging.info("--- 環境変数からの設定値読み込み完了 ---")

# ロギング設定 (INFOレベル以上のメッセージを、タイムスタンプ付きのフォーマットで出力)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# --- データベース関連の関数 ---

# データベースの初期化と接続を確立する関数
def ensure_db():
    logging.info(f"データベース接続/初期化開始: {DB_PATH}")
    # データベースファイルに接続 (ファイルが存在しない場合は作成される)
    conn = sqlite3.connect(DB_PATH)
    # 'seen' テーブルが存在しない場合、作成する
    # id: イベントのユニークID (PRIMARY KEY)、created_at: 登録日時
    conn.execute("""CREATE TABLE IF NOT EXISTS seen(
        id TEXT PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    # 変更を確定
    conn.commit(); 
    logging.info("データベース 'seen' テーブルの存在確認/作成完了")
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
    logging.info(f"新着イベントのフィルタリング開始: 全{len(events)}件")
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
    logging.info(f"新着イベントのフィルタリング完了: {len(out)}件抽出されました")
    return out

# 新しく通知したイベントをデータベースに「既読」として登録する関数
def mark_seen(conn, events):
    logging.info(f"既読としてマークするイベント数: {len(events)}件")
    cur = conn.cursor()
    for e in events:
        # UIDを 'seen' テーブルに挿入 (既に存在する場合は無視する: IGNORE)
        cur.execute("INSERT OR IGNORE INTO seen(id) VALUES(?)", (e["_uid"],))
    # 変更を確定
    conn.commit()
    logging.info("既読イベントのデータベース登録完了 (コミット済み)")

# --- LINE通知関連の関数 ---

# LINE Push Message APIを使ってメッセージを送信する関数
def push_message(to_id, text):
    logging.info(f"LINEメッセージ送信開始 (To: {to_id}) - メッセージ長: {len(text)}文字")
    url = "https://api.line.me/v2/bot/message/push"
    # 認証ヘッダーとコンテンツタイプを設定
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type":"application/json"}
    # 送信先のIDとメッセージの内容 (テキスト) を設定
    # LINEのメッセージ最大文字数に合わせ、テキストを最大4900文字に制限
    body = {"to": to_id, "messages":[{"type":"text","text":text[:4900]}]}
    # APIにPOSTリクエストを送信 (20秒のタイムアウトを設定)
    r = requests.post(url, headers=headers, json=body, timeout=20)
    logging.info(f"LINE API応答ステータス: {r.status_code}")
    # ステータスコードがエラーを示す場合 (4xx, 5xx) は例外を発生させる
    r.raise_for_status()
    logging.info(f"LINEメッセージ送信成功 (To: {to_id})")

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
    logging.info("=== スクリプト処理開始 ===")
    
    # 環境変数 (TOKENとTARGET_IDS) が設定されているかチェック
    if not (TOKEN and TARGET_IDS):
        logging.error("環境変数 LINE_CHANNEL_ACCESS_TOKEN / TARGET_IDS が未設定です。")
        raise SystemExit("環境変数 LINE_CHANNEL_ACCESS_TOKEN / TARGET_IDS が未設定です。")
    
    # 1. イベント情報を含むHTMLを取得
    logging.info("1. HTMLコンテンツの取得開始...")
    html, final_url = fetch_events_html()
    logging.info(f"1. HTMLコンテンツの取得完了。最終URL: {final_url}")
    
    # 2. 取得したHTMLからイベント情報を解析し、イベントリストを取得
    logging.info("2. 取得したHTMLからのイベント情報解析開始...")
    events = parse_events_generic(html, final_url)
    logging.info(f"2. イベント情報解析完了。見つかったイベント数: {len(events)}件")
    
    # イベントが一つも見つからなかった場合の処理
    if not events:
        logging.warning("イベントが見つかりません。parsers.py のセレクタ調整が必要です。")
        logging.info("=== スクリプト処理終了 (警告あり) ===")
        return
    
    # 3. データベースへの接続を確立
    logging.info("3. データベース接続確立処理へ...")
    conn = ensure_db()
    
    # 4. 取得したイベントリストから、データベースに未登録の「新着」イベントを抽出
    logging.info("4. 新着イベントのフィルタリング処理へ...")
    new_events = filter_new(conn, events)
    
    # 新着イベントがなかった場合の処理
    if not new_events:
        logging.info("新着イベントなし。通知スキップ。")
        logging.info("=== スクリプト処理終了 (新着なし) ===")
        return
    
    logging.info(f"新着イベント数: {len(new_events)}件")
    
    # 5. 通知するイベントを MAX_POSTS 件までに制限
    original_new_count = len(new_events)
    new_events = new_events[:MAX_POSTS]
    logging.info(f"5. 通知イベント数を {MAX_POSTS} 件に制限。実際に通知する件数: {len(new_events)}件")
    
    # 6. 新着イベントをまとめて1つのメッセージに整形
    logging.info("6. LINEメッセージへの整形開始...")
    message = "\n\n".join(format_event(e) for e in new_events)
    logging.info(f"6. メッセージ整形完了。メッセージ全体の文字数: {len(message)}")
    
    # 7. ターゲットIDリストの各ユーザー/グループにメッセージを送信
    logging.info(f"7. LINEメッセージ送信開始 (対象ID数: {len(TARGET_IDS)})")
    for i, tid in enumerate(TARGET_IDS, 1):
        try:
            push_message(tid, message)
            logging.info(f"送信成功 {i}/{len(TARGET_IDS)} (ID: {tid})")
        except requests.exceptions.HTTPError as e:
            logging.error(f"LINEメッセージ送信失敗 {i}/{len(TARGET_IDS)} (ID: {tid}): {e}")
        # APIレート制限などを考慮し、送信間に1秒待機
        time.sleep(1.0)
    logging.info("7. 全ターゲットへのLINEメッセージ送信処理完了")
        
    # 8. 通知したイベントをデータベースに既読として登録
    logging.info("8. 通知済みイベントの既読マーク処理へ...")
    mark_seen(conn, new_events)
    
    # 9. 処理結果をロギング
    logging.info(f"9. 処理結果: 新規イベント {original_new_count}件中、{len(new_events)}件を送信・既読マーク完了。")
    logging.info("=== スクリプト処理正常終了 ===")

# スクリプトが直接実行された場合に main 関数を呼び出す
if __name__ == "__main__":
    main()