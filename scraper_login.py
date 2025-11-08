import os
from playwright.sync_api import sync_playwright

LOGIN_URL  = os.getenv("LOGIN_URL")
EVENTS_URL = os.getenv("EVENTS_URL")
USER       = os.getenv("CCONSUL_ID")
PASS       = os.getenv("CCCONSUL_PASSWORD") or os.getenv("CCONSUL_PASSWORD")  # 互換
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; CConsulScraper/1.0)")
WAIT_SELECTOR = os.getenv("WAIT_SELECTOR", "table, .events, .schedule, .list")

# ★ 追加: フィクスチャでログインをスキップ（B/A両方のデバッグで使用）
HTML_FIXTURE = os.getenv("HTML_FIXTURE")

def fetch_events_html():
    # ★ 追加: フィクスチャ指定時はログインせずにローカルHTMLを返す
    if HTML_FIXTURE:
        with open(HTML_FIXTURE, "r", encoding="utf-8") as f:
            html = f.read()
        final_url = EVENTS_URL or "https://example.com/mypage/shigaku/schedule/events/"
        return html, final_url

    # （本番・検証用）従来どおりログインして取得
    if not all([LOGIN_URL, EVENTS_URL, USER, PASS]):
        raise RuntimeError("環境変数 LOGIN_URL / EVENTS_URL / CCONSUL_ID / CCONSUL_PASSWORD を設定してください。")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT)
        page = ctx.new_page()

        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

        user_fields = ['input[name="username"]','input[name="loginId"]','#username','input[type="email"]']
        pass_fields = ['input[name="password"]','#password','input[type="password"]']
        submit_btns = ['button[type="submit"]','input[type="submit"]','.btn-login','button:has-text("ログイン")']

        for sel in user_fields:
            if page.locator(sel).count():
                page.fill(sel, USER)
                break
        for sel in pass_fields:
            if page.locator(sel).count():
                page.fill(sel, PASS)
                break
        for sel in submit_btns:
            if page.locator(sel).count():
                page.click(sel)
                break
        else:
            page.keyboard.press("Enter")

        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.goto(EVENTS_URL, wait_until="domcontentloaded", timeout=30000)

        for css in [s.strip() for s in WAIT_SELECTOR.split(",") if s.strip()]:
            try:
                page.wait_for_selector(css, timeout=8000)
                break
            except:
                pass

        html = page.content()
        final_url = page.url
        browser.close()
        return html, final_url
