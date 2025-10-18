from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List, Dict, Optional

def parse_events_generic(html: str, base_url: str) -> List[Dict[str, Optional[str]]]:
    """
    HTMLからイベント情報（日付、タイトル、リンク）を抽出する。
    1. テーブル形式
    2. 汎用リスト形式
    3. 新しい特定のリスト形式（.row.ttl）
    の順に試行する。
    """
    soup = BeautifulSoup(html, "lxml")
    events = []

    # --- 1. テーブル形式の解析（元のコードのまま） ---
    for tr in soup.select("table tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        date = tds[0].get_text(strip=True)
        title = tds[1].get_text(strip=True)
        a = tr.select_one("a[href]")
        link = urljoin(base_url, a["href"]) if a else None
        if title:
            events.append({"date": date, "title": title, "link": link})
    if events:
        return events

    # --- 2. 汎用リスト形式の解析（元のコードのまま） ---
    # .events .event, .event-item, .schedule .item, li.event などの一般的なリスト構造に対応
    #for el in soup.select(".events .event, .event-item, .schedule .item, li.event"):
        # title_el, date_el, a の検索ロジックは元のコードのまま
        title_el = el.select_one(".title, h3, h4, a")
        date_el  = el.select_one(".date, time")
        a = el.select_one("a[href]")
        
        # データの抽出
        title = title_el.get_text(strip=True) if title_el else None
        link  = urljoin(base_url, a["href"]) if a else None
        date  = date_el.get_text(strip=True) if date_el else None
        
        if title:
            events.append({"date": date, "title": title, "link": link})
            
    if events:
        return events
    
    # --- 3. 新しい特定のリスト形式 (.row.ttl) の解析（追加・修正部分） ---
    
    # イベントリストの要素を取得: <div class="row ttl"> の中の <ul> の中の <li>
    for li in soup.select(".row ttl > ul > li"):
        a_tag = li.select_one("a[href]")
        
        if not a_tag:
            continue

        # リンクの抽出と絶対URLへの変換
        link = urljoin(base_url, a_tag["href"])
        
        # タイトル抽出のため、<a>タグをコピーして余分な<span>タグを削除
        # コピーを作成
        a_copy = BeautifulSoup(str(a_tag), "lxml").select_one('a')

        # 日付要素（<a>タグ内の最初の<span>）を取得
        date_span = a_copy.select_one("span:first-child")
        date_text = date_span.get_text(strip=True) if date_span else None
        
        # 日付や状態を示す全ての<span>タグを削除
        for span in a_copy.find_all("span"):
            span.decompose()
            
        # 残ったテキストがタイトル（<br>タグはスペースに変換）
        title = a_copy.get_text(strip=True).replace('<br>', ' ').strip()
        
        # タイトルが取得できた場合のみイベントとして追加
        if title:
            events.append({
                "date": date_text,
                "title": title,
                "link": link
            })

    return events