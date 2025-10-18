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
    
 # イベントリストの要素を取得: <div class="row ttl"> の中の <ul> の中の <li>
    for li in soup.select(".row.ttl > ul > li"):
        a_tag = li.select_one("a[href]")
        
        if not a_tag:
            continue

        # リンクの抽出と絶対URLへの変換
        link = urljoin(base_url, a_tag["href"])
        
        # --- 日付の抽出 (<a>タグ内の最初の <span>) ---
        date_span = a_tag.select_one("span:first-child")
        date_text = date_span.get_text(strip=True) if date_span else None
        
        # --- タイトルの抽出 ---
        # <a>タグ内の子要素を順に処理し、純粋なテキストのみを結合してタイトルとする
        raw_title_parts = []
        
        # <a>タグ内の全ての子要素（タグとテキスト）をイテレート
        for content in a_tag.contents:
            # contentが文字列（テキストノード）の場合
            if isinstance(content, NavigableString):
                text = str(content).strip()
                if text:
                    raw_title_parts.append(text)
            
            # contentが<br>タグの場合
            elif content.name == 'br':
                raw_title_parts.append(' ') # タイトル内の改行をスペースに変換
                
            # contentが<span>タグで、日付または状態の情報を含む場合、スキップする
            elif content.name == 'span':
                # <span>内のテキストは日付と状態（△残席少、予約中など）なので、ここでは無視
                continue
        
        # タイトルを結合して整形
        title = "".join(raw_title_parts).strip()
        
        # タイトルが取得できた場合のみイベントとして追加
        if title:
            events.append({
                "date": date_text,
                "title": title,
                "link": link
            })

    return events