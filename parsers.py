from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List, Dict, Optional
import sys

def _text_after_first_br(a_tag) -> Optional[str]:
    """
    <a> の中で「最初の <br>」以降のテキストだけを抽出する。
    子要素（span など）も含めて連結し、前後空白を整える。
    """
    if not a_tag:
        return None
    parts = []
    seen_br = False
    for node in a_tag.children:
        # <br> に遭遇するまでは読み飛ばし
        if getattr(node, "name", None) == "br":
            seen_br = True
            continue
        if not seen_br:
            continue
        # タグならテキスト、文字ならそのまま
        get_text = getattr(node, "get_text", None)
        parts.append(get_text(strip=True) if get_text else str(node).strip())
    title = " ".join(p for p in parts if p)
    return title or None

def _parse_row_ttl_events(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Optional[str]]]:
    """
    しがく「イベント」タブがアクティブなページ専用。
    - li.is-active a[href*="/schedule/events"] or テキストが「その他イベント」
    - その直後の <div class="row ttl"> 配下の <ul><li><a>…</a></li> を列挙
    """
    print("--- DEBUG: 専用パーサ(row.ttl)を試行中 ---", file=sys.stderr)

    active = soup.select_one('li a[href*="/schedule/events"]')
    if not active:
        cand = soup.select_one('li a')
        if not (cand and "その他イベント" in cand.get_text(strip=True)):
            print("--- DEBUG: イベントタブはアクティブではないため専用パーサをスキップ ---", file=sys.stderr)
            return []

    # タブ群 <div class="row"> のすぐ次にある <div class="row ttl"> を狙う
    tabs_first = soup.select_one('div.row > ul li.tabs-title')
    if tabs_first:
        row_ttl = tabs_first.find_parent("div", class_="row").find_next("div", class_="row ttl")
    else:
        row_ttl = soup.select_one("div.row.ttl")

    if not row_ttl:
        print("--- DEBUG: row.ttl が見つからない ---", file=sys.stderr)
        return []

    li_elements = row_ttl.select("ul > li")
    print(f"--- DEBUG: row.ttl 内の li 要素数: {len(li_elements)} ---", file=sys.stderr)

    events: List[Dict[str, Optional[str]]] = []
    for i, li in enumerate(li_elements, 1):
        print(f"--- DEBUG: row.ttl li {i} 件目 処理 ---", file=sys.stderr)
        a_tag = li.select_one("a[href]")
        if not a_tag:
            print(f"--- DEBUG: li {i}: <a> なし ---", file=sys.stderr)
            continue

        link = urljoin(base_url, a_tag["href"])
        # a_tag を独立に再パース（span除去前に日付だけ確保）
        a_copy = BeautifulSoup(str(a_tag), "lxml").select_one("a")

        # 先頭の <span> を日付として読む（例: 2025.11.02（日）19:30）
        date_span = a_copy.select_one("span:first-child")
        date_text = date_span.get_text(strip=True) if date_span else None
        print(f"--- DEBUG: li {i}: 抽出日付: {date_text} ---", file=sys.stderr)

        # タイトルは <br> 以降のテキストのみ
        title = _text_after_first_br(a_copy)
        # もし <br> がない等で None の場合はフォールバックで a 全体テキスト
        if not title:
            title = a_copy.get_text(" ", strip=True)

        print(f"--- DEBUG: li {i}: 抽出タイトル: {title} ---", file=sys.stderr)
        print(f"--- DEBUG: li {i}: 抽出リンク: {link} ---", file=sys.stderr)

        if title:
            events.append({"date": date_text, "title": title, "link": link})

    print(f"--- DEBUG: 専用パーサ(row.ttl) 検出件数: {len(events)} ---", file=sys.stderr)
    return events

def parse_events_generic(html: str, base_url: str) -> List[Dict[str, Optional[str]]]:
    """
    HTMLからイベント情報（日付、タイトル、リンク）を抽出する。
    優先順:
      0) しがく「イベント」専用（row.ttl）
      1) テーブル形式
      2) 汎用リスト形式
    """
    print("--- DEBUG: parse_events_generic 開始 ---", file=sys.stderr)
    soup = BeautifulSoup(html, "lxml")
    events: List[Dict[str, Optional[str]]] = []

    # --- 0. しがく「イベント」専用（row.ttl） ---
    specialized = _parse_row_ttl_events(soup, base_url)
    if specialized:
        print("--- DEBUG: 0. 専用(row.ttl)で検出。処理を終了 ---", file=sys.stderr)
        return specialized
    print("--- DEBUG: 0. 専用(row.ttl)では検出なし。次へ ---", file=sys.stderr)

    # --- 1. テーブル形式の解析 ---
    print("--- DEBUG: 1. テーブル形式の解析を試行中 ---", file=sys.stderr)
    for i, tr in enumerate(soup.select("table tbody tr"), 1):
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
        print(f"--- DEBUG: 1. テーブル形式で {len(events)} 件のイベントを検出。処理を終了 ---", file=sys.stderr)
        return events
    print("--- DEBUG: 1. テーブル形式ではイベントを検出せず ---", file=sys.stderr)

    # --- 2. 汎用リスト形式の解析 ---
    print("--- DEBUG: 2. 汎用リスト形式の解析を試行中 ---", file=sys.stderr)
    list_elements = soup.select(".events .event, .event-item, .schedule .item, li.event")
    print(f"--- DEBUG: 2. 検出された汎用リスト要素の数: {len(list_elements)} ---", file=sys.stderr)

    for el in list_elements:
        title_el = el.select_one(".title, h3, h4, a")
        date_el  = el.select_one(".date, time")
        a = el.select_one("a[href]")

        title = title_el.get_text(strip=True) if title_el else None
        link  = urljoin(base_url, a["href"]) if a else None
        date  = date_el.get_text(strip=True) if date_el else None

        if title:
            events.append({"date": date, "title": title, "link": link})

    if events:
        print(f"--- DEBUG: 2. 汎用リスト形式で {len(events)} 件のイベントを検出。処理を終了 ---", file=sys.stderr)
        return events

    print("--- DEBUG: 2. 汎用リスト形式でもイベントを検出できず ---", file=sys.stderr)
    print("--- DEBUG: parse_events_generic 終了（検出0件） ---", file=sys.stderr)
    return events
