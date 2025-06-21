import os, requests, feedparser
from datetime import datetime, timedelta
from telegram import Bot
from bs4 import BeautifulSoup

# 1) Метрики (все бесплатные публичные источники)
def fetch_metrics():
    now = datetime.utcnow()
    # DXY через exchangerate.host
    rates = requests.get('https://api.exchangerate.host/timeseries', params={
        'start_date': (now - timedelta(days=1)).strftime('%Y-%m-%d'),
        'end_date': now.strftime('%Y-%m-%d'),
        'base': 'USD', 'symbols': 'EUR'
    }).json()['rates']
    dates = sorted(rates.keys())
    dxy = (rates[dates[-1]]['EUR'] - rates[dates[0]]['EUR']) / rates[dates[0]]['EUR'] * 100

    # Crypto Fear & Greed
    fgi = int(requests.get('https://api.alternative.me/fng/').json()['data'][0]['value'])

    # Altseason Index
    alt = requests.get('https://api.altseason.com/').json().get('index', 0)

    # Crypto Market Cap
    cap = requests.get('https://api.coingecko.com/api/v3/global')\
                 .json()['data']['total_market_cap']['usd']

    # US 10Y и M2SL через FRED (публично, без ключей)
    fred = 'https://api.stlouisfed.org/fred/series/observations'
    dgs10 = float(requests.get(fred, params={
        'series_id':'DGS10','file_type':'json',
        'observation_start':(now-timedelta(days=2)).strftime('%Y-%m-%d')
    }).json()['observations'][-1]['value'])
    m2 = float(requests.get(fred, params={
        'series_id':'M2SL','file_type':'json',
        'observation_start':(now-timedelta(days=2)).strftime('%Y-%m-%d')
    }).json()['observations'][-1]['value'])

    return {'DXY':dxy,'FGI':fgi,'ALT':alt,'CAP':cap,'DGS10':dgs10,'M2':m2}

# 2) Новости — RSS-фиды (бесплатно)
def fetch_news():
    feeds = [
        'http://feeds.reuters.com/reuters/businessNews',
        'https://www.ft.com/?edition=international&format=rss',
        'http://feeds.bbci.co.uk/news/world/rss.xml'
    ]
    kws = ['econom','polit','crypto','market']
    out = []
    for url in feeds:
        for e in feedparser.parse(url).entries:
            title = e.title.lower()
            if any(k in title for k in kws):
                out.append({'title':e.title,'url':e.link})
    return out[:5]

# 3) Твиты — скрейпинг через Nitter (бесплатно)
def fetch_tweets(user):
    url = f'https://nitter.net/{user}'
    r = requests.get(url, headers={'User-Agent':'Mozilla/5.0'})
    soup = BeautifulSoup(r.text, 'html.parser')
    tweets = []
    for div in soup.select('.timeline-item')[:3]:
        txt = div.select_one('.tweet-content').get_text(strip=True)
        tm = div.select_one('a.datetime').get_text(strip=True)
        link = 'https://twitter.com' + div.select_one('a.tweet-link')['href']
        tweets.append({'user':user,'text':txt,'time':tm,'url':link})
    return tweets

# 4) Тематическая картинка — Unsplash source (без ключей)
def fetch_image():
    return 'https://source.unsplash.com/1200x400/?finance,abstract'

# 5) Сборка и отправка
def build_and_send():
    today = datetime.utcnow().strftime('%d.%m.%Y')
    m = fetch_metrics()
    news = fetch_news()
    trump = fetch_tweets('realDonaldTrump')
    infl = fetch_tweets('elonmusk') + fetch_tweets('cz_binance')
    img = fetch_image()

    header = (
        f"🗓️ *Ежедневный дайджест — {today}*\n\n"
        f"🔔 *Метрики:* 🇺🇸10Y {m['DGS10']:+.2f}% | 💵DXY {m['DXY']:+.2f}% | "
        f"😱FGI {m['FGI']} | 🔀ALT {m['ALT']}% | 💸M2 {m['M2']:+.2f}% | 🌐Cap ${m['CAP']:.0f}\n\n—\n"
    )

    body = "### Новости\n" + "\n".join(
        f"{i+1}. [{a['title']}]({a['url']})" for i,a in enumerate(news)
    )
    body += "\n\n### 💬 Твиты Дональда Трампа\n" + "\n".join(
        f"• [{t['time']}]({t['url']}): {t['text']}" for t in trump
    )
    body += "\n\n### 🚀 Крипто-лидеры\n" + "\n".join(
        f"• [{t['user']}] [{t['time']}]({t['url']}): {t['text']}" for t in infl
    )

    text = header + body + f"\n\n![img]({img})"

    Bot(token=os.getenv('TELEGRAM_TOKEN')).send_message(
        chat_id=os.getenv('CHANNEL_ID'),
        text=text,
        parse_mode='MarkdownV2',
        disable_web_page_preview=False
    )

if __name__=="__main__":
    build_and_send()
