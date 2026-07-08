import json, os, requests

ALERTS_PATH = os.path.join(os.path.dirname(__file__), 'data', 'alerts.json')

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def load_alerts():
    if not os.path.exists(ALERTS_PATH):
        return []
    with open(ALERTS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_alerts(alerts):
    os.makedirs(os.path.dirname(ALERTS_PATH), exist_ok=True)
    with open(ALERTS_PATH, 'w', encoding='utf-8') as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)

def _tw_listed(code):
    """上市股（TWSE）收盤價"""
    url = f'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?stockNo={code}&response=json'
    r = requests.get(url, headers=HEADERS, timeout=10)
    data = r.json()
    if data.get('stat') != 'OK' or not data.get('data'):
        return None, None, None
    rows = data['data']
    if len(rows) < 2:
        return None, None, None
    # 最後兩個交易日
    def parse_price(row):
        p = row[6].replace(',', '')  # 收盤價欄位
        return float(p) if p != '--' else None
    price = parse_price(rows[-1])
    prev  = parse_price(rows[-2])
    name  = data.get('title', '').split(' ')[-1] if data.get('title') else code
    return price, prev, name

def _tw_otc(code):
    """上櫃股（TPEx）收盤價"""
    import datetime
    today = datetime.date.today()
    ym = f'{today.year - 1911}/{today.month:02d}'
    url = f'https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={ym}&se=AL&s=0,asc&o=json'
    r = requests.get(url, headers=HEADERS, timeout=10)
    data = r.json()
    rows = data.get('aaData', [])
    # 找目標代號的最後兩筆（先按日期倒序）
    matches = [row for row in rows if row[0].strip() == code]
    if len(matches) < 1:
        return None, None, None
    def parse_price(row):
        p = str(row[2]).replace(',', '')
        return float(p) if p not in ('--', '') else None
    price = parse_price(matches[0])
    prev  = parse_price(matches[1]) if len(matches) >= 2 else price
    name  = matches[0][1] if matches else code
    return price, prev, name

def _us_stock(code):
    """美股用 yfinance"""
    import yfinance as yf
    hist = yf.Ticker(code).history(period='2d')
    if hist.empty:
        return None, None, code
    price = hist['Close'].iloc[-1]
    prev  = hist['Close'].iloc[-2] if len(hist) >= 2 else price
    return price, prev, code

def get_stock_price(code):
    code = code.upper().strip()
    is_tw = len(code) == 4 and code.isdigit()

    try:
        if is_tw:
            price, prev, name = _tw_listed(code)
            if price is None:
                price, prev, name = _tw_otc(code)
        else:
            price, prev, name = _us_stock(code)

        if price is None:
            return f'找不到股票代碼「{code}」（可能非交易日或代碼有誤）'

        prev  = prev or price
        chg   = price - prev
        pct   = chg / prev * 100 if prev else 0
        arrow = '▲' if chg >= 0 else '▼'
        label = f'{code} {name}' if name and name != code else code
        return f'📈 {label}\n收盤價：{price:.2f}\n{arrow} {abs(chg):.2f}（{abs(pct):.2f}%）'
    except Exception as e:
        return f'股價查詢失敗（{code}）：{str(e)}'

def _get_price_for_alert(code):
    """回傳 (price, prev)，供 check_alerts 使用"""
    is_tw = len(code) == 4 and code.isdigit()
    if is_tw:
        price, prev, _ = _tw_listed(code)
        if price is None:
            price, prev, _ = _tw_otc(code)
    else:
        price, prev, _ = _us_stock(code)
    return price, prev

def check_alerts(line_bot_api):
    alerts = load_alerts()
    triggered = []
    remaining = []

    for a in alerts:
        code      = a['code']
        direction = a['direction']
        threshold = a['pct']
        user_id   = a.get('user_id', '')

        try:
            price, prev = _get_price_for_alert(code)
            if price is None or prev is None:
                remaining.append(a)
                continue
            pct = (price - prev) / prev * 100

            hit = (direction == '漲' and pct >= threshold) or \
                  (direction == '跌' and pct <= -threshold)

            if hit and user_id:
                msg = f'🔔 股票提醒觸發！\n{code} {direction}{threshold}%\n現在：{price:.2f}（{pct:+.2f}%）'
                from linebot.models import TextSendMessage
                line_bot_api.push_message(user_id, TextSendMessage(text=msg))
                triggered.append(a)
            else:
                remaining.append(a)
        except Exception:
            remaining.append(a)

    if triggered:
        save_alerts(remaining)
