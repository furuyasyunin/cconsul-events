from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List, Dict, Optional
import sys

def parse_events_generic(html: str, base_url: str) -> List[Dict[str, Optional[str]]]:
    """
    HTMLからイベント情報（日付、タイトル、リンク）を抽出する。
    1. テーブル形式
    2. 汎用リスト形式
    3. 新しい特定のリスト形式（.row.ttl）
    の順に試行する。
    """
    print("--- DEBUG: parse_events_generic 開始 ---", file=sys.stderr)
    soup = BeautifulSoup(html, "lxml")
    events = []

    # --- 1. テーブル形式の解析 ---
    print("--- DEBUG: 1. テーブル形式の解析を試行中 ---", file=sys.stderr)
    for i, tr in enumerate(soup.select("table tbody tr")):
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
    # 検索セレクタを修正（元のコードではコメントアウトされていたため）
    list_elements = soup.select(".events .event, .event-item, .schedule .item, li.event")
    print(f"--- DEBUG: 2. 検出された汎用リスト要素の数: {len(list_elements)} ---", file=sys.stderr)

    for el in list_elements:
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
        print(f"--- DEBUG: 2. 汎用リスト形式で {len(events)} 件のイベントを検出。処理を終了 ---", file=sys.stderr)
        return events
    print("--- DEBUG: 2. 汎用リスト形式ではイベントを検出せず ---", file=sys.stderr)
    
    # --- 3. 新しい特定のリスト形式 (.row.ttl) の解析 ---
    print("--- DEBUG: 3. 特定のリスト形式 (.row ttl) の解析を試行中 ---", file=sys.stderr)
    
    # イベントリストの要素を取得: <div class="row ttl"> の中の <ul> の中の <li>
    li_elements = soup.select(".row.ttl > ul > li")
    print(f"--- DEBUG: 3. 検出された .row ttl > ul > li 要素の数: {len(li_elements)} ---", file=sys.stderr)
    
    for i, li in enumerate(li_elements):
        print(f"--- DEBUG: 3. {i+1} 番目の li 要素の処理開始 ---", file=sys.stderr)
        a_tag = li.select_one("a[href]")
        
        if not a_tag:
            print(f"--- DEBUG: 3. {i+1} 番目の li に <a> タグなし。スキップ ---", file=sys.stderr)
            continue

        # リンクの抽出と絶対URLへの変換
        link = urljoin(base_url, a_tag["href"])
        print(f"--- DEBUG: 3. {i+1} 番目の li リンク抽出: {link} ---", file=sys.stderr)
        
        # タイトル抽出のため、<a>タグをコピーして余分な<span>タグを削除
        # コピーを作成
        # BeautifulSoupでタグをコピーする際は、そのタグを一旦文字列化し、再度BeautifulSoupでパースするのが確実
        a_copy = BeautifulSoup(str(a_tag), "lxml").select_one('a')
        print(f"--- DEBUG: 3. {i+1} 番目の li <a> タグをコピーし再パース完了 ---", file=sys.stderr)


        # 日付要素（<a>タグ内の最初の<span>）を取得
        date_span = a_copy.select_one("span:first-child")
        date_text = date_span.get_text(strip=True) if date_span else None
        print(f"--- DEBUG: 3. {i+1} 番目の li 日付要素(span:first-child)抽出: {date_text} ---", file=sys.stderr)
        
        # 日付や状態を示す全ての<span>タグを削除
        span_count = len(a_copy.find_all("span"))
        for span in a_copy.find_all("span"):
            span.decompose()
        print(f"--- DEBUG: 3. {i+1} 番目の li {span_count} 個の <span> タグを削除完了 ---", file=sys.stderr)
            
        # 残ったテキストがタイトル（<br>タグはスペースに変換）
        # <br>タグの処理は、get_textの引数separatorで代替可能だが、元のロジックを維持してデバッグ
        a_copy_text_before_br_replace = a_copy.get_text(strip=True)
        title = a_copy_text_before_br_replace.replace('<br>', ' ').strip()
        print(f"--- DEBUG: 3. {i+1} 番目の li 抽出されたタイトル: {title} ---", file=sys.stderr)
        
        # タイトルが取得できた場合のみイベントとして追加
        if title:
            events.append({
                "date": date_text,
                "title": title,
                "link": link
            })
            print(f"--- DEBUG: 3. {i+1} 番目の li イベント情報をリストに追加完了 ---", file=sys.stderr)
        else:
            print(f"--- DEBUG: 3. {i+1} 番目の li タイトルが空のためスキップ ---", file=sys.stderr)

    print(f"--- DEBUG: 3. 特定のリスト形式で {len(events)} 件のイベントを検出 ---", file=sys.stderr)
    print("--- DEBUG: parse_events_generic 終了 ---", file=sys.stderr)
    return events