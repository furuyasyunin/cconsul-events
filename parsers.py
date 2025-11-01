# parsers.py
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List, Dict, Optional
import sys

def _text_after_first_br(a_tag) -> Optional[str]:
    """<a> 内の最初の <br> 以降だけをタイトルとして抽出。"""
    if not a_tag:
        return None
    parts, seen_br = [], False
    for node in a_tag.children:
        if getattr(node, "name", None) == "br":
            seen_br = True
            continue
        if not seen_br:
            continue
        get_text = getattr(node, "get_text", None)
        parts.append(get_text(strip=True) if get_text else str(node).strip())
    title = " ".join([p for p in parts if p])
    return title or None

def _parse_row_ttl_events(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Optional[str]]]:
    """しがく『イベント』ページ専用。row.ttl を優先的に読む。"""
    print(f"--- DEBUG[A]: row.ttl 試行 base_url={base_url}", file=sys.stderr)

    url_says_events = "/schedule/events" in (base_url or "")
    dom_has_events_tab = bool(soup.select_one('li.tabs-title a[href*="/schedule/events"]'))
    is_active_tab = bool(soup.select_one('li.tabs-title.is-active a[href*="/schedule/events"]'))
    print(f"--- DEBUG[A]: 判定 url_says_events={url_says_events}, dom_has_events_tab={dom_has_events_tab}, is_active_tab={is_active_tab}", file=sys.stderr)

    if not (url_says_events or dom_has_events_tab or is_active_tab):
        print("--- DEBUG[A]: row.ttl 条件を満たさずスキップ", file=sys.stderr)
        return []

    # タブ直後→なければ最初の row.ttl
    row_ttl = None
    tabs_first = soup.select_one('div.row > ul li.tabs-title')
    if tabs_first:
        row_ttl = tabs_first.find_parent("div", class_="row").find_next("div", class_="row ttl")
    if not row_ttl:
        row_ttl = soup.select_one("div.row.ttl")
    if not row_ttl:
        print("--- DEBUG[A]: .row.ttl 見つからず", file=sys.stderr)
        return []

    lis = row_ttl.select("ul > li")
    print(f"--- DEBUG[A]: row.ttl 内 li 件数={len(lis)}", file=sys.stderr)

    out: List[Dict[str, Optional[str]]] = []
    for i, li in enumerate(lis, 1):
        a = li.select_one("a[href]")
        if not a:
            print(f"--- DEBUG[A]: li {i}: <a> なし", file=sys.stderr)
            continue

        link = urljoin(base_url, a["href"])
        a_copy = BeautifulSoup(str(a), "lxml").select_one("a")

        date_span = a_copy.select_one("span:first-child")
        date_text = date_span.get_text(strip=True) if date_span else None

        title = _text_after_first_br(a_copy)
        if not title:  # フォールバック：span除去後の全体テキスト
            for sp in a_copy.find_all("span"):
                sp.decompose()
            title = a_copy.get_text(" ", strip=True)

        print(f"--- DEBUG[A]: li {i}: date='{date_text}', title='{title}', link='{link}'", file=sys.stderr)
        if title:
            out.append({"date": date_text, "title": title, "link": link})

    print(f"--- DEBUG[A]: row.ttl 収集件数={len(out)}", file=sys.stderr)
    return out

def parse_events_generic(html: str, base_url: str) -> List[Dict[str, Optional[str]]]:
    """優先順：0) row.ttl専用 → 1) テーブル → 2) 汎用リスト"""
    print("--- DEBUG[A]: parse_events_generic 開始 ---", file=sys.stderr)
    soup = BeautifulSoup(html, "lxml")

    # 0) row.ttl
    ev = _parse_row_ttl_events(soup, base_url)
    if ev:
        print("--- DEBUG[A]: row.ttl 命中 → return", file=sys.stderr)
        return ev
    print("--- DEBUG[A]: row.ttl 不発 → 次へ", file=sys.stderr)

    # 1) テーブル
    print("--- DEBUG[A]: テーブル試行", file=sys.stderr)
    table_out: List[Dict[str, Optional[str]]] = []
    for tr in soup.select("table tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        date = tds[0].get_text(strip=True)
        title = tds[1].get_text(strip=True)
        a = tr.select_one("a[href]")
        link = urljoin(base_url, a["href"]) if a else None
        if title:
            table_out.append({"date": date, "title": title, "link": link})
    if table_out:
        print(f"--- DEBUG[A]: テーブル検出 {len(table_out)} 件 → return", file=sys.stderr)
        return table_out
    print("--- DEBUG[A]: テーブル不発 → 次へ", file=sys.stderr)

    # 2) 汎用リスト
    print("--- DEBUG[A]: 汎用リスト試行", file=sys.stderr)
    out: List[Dict[str, Optional[str]]] = []
    for el in soup.select(".events .event, .event-item, .schedule .item, li.event"):
        title_el = el.select_one(".title, h3, h4, a")
        date_el  = el.select_one(".date, time")
        a = el.select_one("a[href]")
        title = title_el.get_text(strip=True) if title_el else None
        link  = urljoin(base_url, a["href"]) if a else None
        date  = date_el.get_text(strip=True) if date_el else None
        if title:
            out.append({"date": date, "title": title, "link": link})

    if out:
        print(f"--- DEBUG[A]: 汎用リスト検出 {len(out)} 件 → return", file=sys.stderr)
        return out

    print("--- DEBUG[A]: 何も検出できず（0件） ---", file=sys.stderr)
    return []