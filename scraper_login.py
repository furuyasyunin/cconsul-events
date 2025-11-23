import os
from playwright.sync_api import sync_playwright

# 1. 環境変数の取得と表示
print("--- 環境変数の設定確認 ---")
LOGIN_URL  = os.getenv("LOGIN_URL")
EVENTS_URL = os.getenv("EVENTS_URL")
USER       = os.getenv("CCONSUL_ID")
PASS       = os.getenv("CCONSUL_PASSWORD")
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; CConsulScraper/1.0)")
WAIT_SELECTOR = os.getenv("WAIT_SELECTOR", "table, .events, .schedule, .list")

print(f"LOGIN_URL: {LOGIN_URL}")
print(f"EVENTS_URL: {EVENTS_URL}")
print(f"USER (ID): {'***' if USER else '未設定'}")
print(f"USER_AGENT: {USER_AGENT}")
print(f"WAIT_SELECTOR: {WAIT_SELECTOR}")
print("--------------------------")

def fetch_events_html():
    if not all([LOGIN_URL, EVENTS_URL, USER, PASS]):
        print("エラー: 必要な環境変数が設定されていません。")
        raise RuntimeError("環境変数 LOGIN_URL / EVENTS_URL / CCONSUL_ID / CCONSUL_PASSWORD を設定してください。")

    print("Playwrightを起動します...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        print("ブラウザ (Chromium, headless=True) を起動しました。")
        ctx = browser.new_context(user_agent=USER_AGENT)
        page = ctx.new_page()
        print(f"新しいページコンテキストを作成しました (User-Agent: {USER_AGENT})。")

        # 2. ログインページへのアクセス
        print(f"ログインURLへ移動中: {LOGIN_URL}")
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            print(f"ログインページに到達しました。現在のURL: {page.url}")
        except Exception as e:
            print(f"エラー: ログインURLへの移動中にタイムアウトまたはエラーが発生しました: {e}")
            browser.close()
            raise

        # 3. ログイン処理
        print("--- ログイン情報の入力開始 ---")
        user_fields = ['input[name="username"]','input[name="loginId"]','#username','input[type="email"]']
        pass_fields = ['input[name="password"]','#password','input[type="password"]']
        submit_btns = ['button[type="submit"]','input[type="submit"]','.btn-login','button:has-text("ログイン")']

        user_filled = False
        for sel in user_fields:
            if page.locator(sel).count():
                page.fill(sel, USER)
                print(f"ユーザー名を入力しました。セレクタ: {sel}")
                user_filled = True
                break
        if not user_filled:
            print("警告: ユーザー名入力欄のセレクタが見つかりませんでした。")
        
        pass_filled = False
        for sel in pass_fields:
            if page.locator(sel).count():
                page.fill(sel, PASS)
                print(f"パスワードを入力しました。セレクタ: {sel}")
                pass_filled = True
                break
        if not pass_filled:
            print("警告: パスワード入力欄のセレクタが見つかりませんでした。")

        submit_clicked = False
        for sel in submit_btns:
            if page.locator(sel).count():
                page.click(sel)
                print(f"ログインボタンをクリックしました。セレクタ: {sel}")
                submit_clicked = True
                break
        else:
            print("警告: 適切なログインボタンが見つからなかったため、Enterキーを押下します。")
            page.keyboard.press("Enter")
            submit_clicked = True

        print("ログイン処理完了。次のページ読み込みを待機します...")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            print(f"ログイン後のページ読み込み完了。現在のURL: {page.url}")
        except Exception as e:
            print(f"エラー: ログイン後のページ読み込み中にタイムアウトまたはエラーが発生しました: {e}")
            # ログイ失敗の可能性
            # browser.close()
            # raise

        # 4. イベントURLへのアクセス
        print(f"イベントURLへ移動中: {EVENTS_URL}")
        try:
            page.goto(EVENTS_URL, wait_until="domcontentloaded", timeout=30000)
            print(f"イベントページに到達しました。現在のURL: {page.url}")
        except Exception as e:
            print(f"エラー: イベントURLへの移動中にタイムアウトまたはエラーが発生しました: {e}")
            browser.close()
            raise

        # 5. 待機セレクタの確認
        wait_selectors = [s.strip() for s in WAIT_SELECTOR.split(",") if s.strip()]
        print(f"表示完了を待機するセレクタ: {wait_selectors}")
        
        selector_found = False
        for css in wait_selectors:
            try:
                print(f"セレクタ '{css}' の出現を待機中 (最大8秒)...")
                page.wait_for_selector(css, timeout=8000)
                print(f"セレクタ '{css}' が見つかりました。待機を終了します。")
                selector_found = True
                break
            except:
                print(f"セレクタ '{css}' は見つかりませんでした。次を試行します。")
                pass
        
        if not selector_found and wait_selectors:
            print("警告: 指定された待機セレクタがすべて見つからなかったため、ページの取得に進みます。")

        # 6. HTMLの取得と終了
        print("ページのHTMLコンテンツを取得します...")
        html = page.content()
        final_url = page.url
        
        print(f"最終的なURL: {final_url}")
        print(f"取得したHTMLの長さ: {len(html)} 文字")
        print(f"取得したHTML: {html} 文字")
        
        browser.close()
        print("ブラウザを閉じました。処理を終了します。")
        return html, final_url

# スクリプトとして実行された場合のログを追記することもできます
if __name__ == '__main__':
    try:
        # この部分で fetch_events_html() を呼び出すと実際に実行されます
        # html, final_url = fetch_events_html()
        # print(f"\n最終結果のURL: {final_url}")
        pass
    except RuntimeError as e:
        # 環境変数エラーなどのログ
        # print(e)
        pass