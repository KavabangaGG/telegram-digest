import os, requests, feedparser, openai
from datetime import datetime, timedelta
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

# 1) Сбор макро-и крипто-метрик
def fetch_metrics():
    now = datetime.utcnow()
    # US 10Y через FRED
    fred = requests.get(
        'https://api.stlouisfed.org/fred/series/observations',
        params={
            'series_id': 'DGS10',
            'api_key': os.getenv('FRED_KEY'),
            'file_type': 'json',
            'observation_start': (now - timedelta(days=2)).strftime('%Y-%m-%d')
        }
    ).json()['observations'][-1]
    dgs10 = float(fred['value'])

    # DXY proxy (USD→EUR)
    xr = requests.get(
        'https://api.exchangerate.host/timeseries',
        params={
            'start_date': (now - timedelta(days=1)).strftime('%Y-%m-%d'),
            'end_date': now.strftime('%Y-%m-%d'),
            'base': 'USD', 'symbols': 'EUR'
        }
    ).json()['rates']
    dates = sorted(xr.keys())
    dxy = (xr[dates[-1]]['EUR'] - xr[dates[0]]['EUR']) / xr[dates[0]]['EUR'] * 100

    # Crypto Fear & Greed
    fgi = int(requests.get('https://api.alternative.me/fng/').json()['data'][0]['value'])

    # Altseason Index
    alt = requests.get('https://api.altseason.com/').json().get('index', 0)

    # Crypto market cap via CoinGecko
    cap = requests.get('https://api.coingecko.com/api/v3/global') \
               .json()['data']['total_market_cap']['usd']

    # M2 (US) via FRED M2SL
    m2 = float(requests.get(
        'https://api.stlouisfed.org/fred/series/observations',
        params={
            'series_id': 'M2SL',
            'api_key': os.getenv('FRED_KEY'),
            'file_type': 'json',
            'observation_start': (now - timedelta(days=2)).strftime('%Y-%m-%d')
        }
    ).json()['observations'][-1]['value'])

    return {
        'DGS10': dgs10,
        'DXY': dxy,
        'FGI': fgi,
        'ALT': alt,
        'M2': m2,
        'CAP': cap
    }

# 2) Сбор новостей (NewsAPI + RSS-фолбек)
def fetch_news():
    kws = ['экономика', 'политика', 'крипто', 'биржа']
    r = requests.get(
        'https://newsapi.org/v2/top-headlines',
        params={
            'apiKey': os.getenv('NEWSAPI_KEY'),
            'language': 'ru',
            'q': ' OR '.join(kws),
            'pageSize': 5
        }
    )
    arts = r.json().get('articles', [])
    if arts:
        return [{'title': a['title'], 'url': a['url']} for a in arts]

    # Фолбек по RSS
    feeds = [
        'http://feeds.reuters.com/reuters/businessNews',
        'https://www.ft.com/?edition=international&format=rss'
    ]
    out = []
    for url in feeds:
        for e in feedparser.parse(url).entries:
            if any(k in e.title.lower() for k in kws):
                out.append({'title': e.title, 'url': e.link})
    return out[:5]

# 3) Сбор твитов
def fetch_tweets(users):
    out = []
    for u in users:
        r = requests.get(
            'https://api.twitter.com/2/tweets/search/recent',
            params={'query': f'from:{u} -is:retweet', 'max_results': 3},
            headers={'Authorization': f'Bearer {os.getenv("TW_BEARER")}'}
        )
        for t in r.json().get('data', []):
            out.append({
                'user': u,
                'text': t['text'],
                'time': t['created_at'],
                'url': f'https://twitter.com/{u}/status/{t["id"]}'
            })
    return out

# 4) Сбор картинки из Unsplash
def fetch_image():
    r = requests.get(
        'https://api.unsplash.com/photos/random',
        params={'query': 'finance abstract', 'orientation': 'landscape'},
        headers={'Authorization': f'Client-ID {os.getenv("UNSPLASH_ACCESS_KEY")}'}
    )
    return r.json().get('urls', {}).get('regular', '')

# 5) Сборка текста и отправка в Telegram
def build_and_send():
    today = datetime.utcnow().strftime('%d.%m.%Y')
    m = fetch_metrics()
    news = fetch_news()
    trump = fetch_tweets(['realDonaldTrump'])
    leaders = fetch_tweets(['elonmusk', 'cz_binance'])
    img = fetch_image()

    header = (
        f"🗓️ *Ежедневный дайджест — {today}*\n\n"
        f"🔔 *Метрики:* 🇺🇸10Y {m['DGS10']:+.2f}% | 💵DXY {m['DXY']:+.2f}% | "
        f"😱FGI {m['FGI']} | 🔀ALT {m['ALT']}% | 💸M2 {m['M2']:+.2f}% | 🌐Cap ${m['CAP']:.0f}\n\n—\n"
    )

    body = "### Новости\n"
    for i, a in enumerate(news, 1):
        body += f"{i}. [{a['title']}]({a['url']})\n"

    body += "\n### Твиты Трампа\n"
    for t in trump:
        body += f"• [{t['time']}]({t['url']}): {t['text']}\n"

    body += "\n### Крипто-лидеры\n"
    for t in leaders:
        body += f"• [{t['user']} · {t['time']}]({t['url']}): {t['text']}\n"

    text = header + body + f"\n![img]({img})"

    Bot(token=os.getenv('TELEGRAM_TOKEN')).send_message(
        chat_id=os.getenv('CHANNEL_ID'),
        text=text,
        parse_mode='MarkdownV2'
    )

if __name__ == "__main__":
    build_and_send()
