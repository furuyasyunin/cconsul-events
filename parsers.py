from bs4 import BeautifulSoup
from urllib.parse import urljoin

def parse_events_generic(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    events = []

    # テーブル形式（1列目:日付, 2列目:タイトル, リンクはa要素）
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

    # カード/リスト形式
    for el in soup.select(".events .event, .event-item, .schedule .item, li.event"):
        title_el = el.select_one(".title, h3, h4, a")
        date_el  = el.select_one(".date, time")
        a = el.select_one("a[href]")
        title = title_el.get_text(strip=True) if title_el else None
        link  = urljoin(base_url, a["href"]) if a else None
        date  = date_el.get_text(strip=True) if date_el else None
        if title:
            events.append({"date": date, "title": title, "link": link})

    return events
