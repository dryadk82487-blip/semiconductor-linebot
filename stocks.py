import json, os, requests

ALERTS_PATH = os.path.join(os.path.dirname(__file__), 'data', 'alerts.json')

def load_alerts():
    if not os.path.exists(ALERTS_PATH):
        return []
    with open(ALERTS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_alerts(alerts):
    os.makedirs(os.path.dirname(ALERTS_PATH), exist_ok=True)
    with open(ALERTS_PATH, 'w', encoding='utf-8') as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)

def get_stock_price(code):
    # 台股加 .TW，美股直接查
    try:
        import yfinance as yf
        suffix = '.TW' if (len(code) == 4 and code.isdigit()) else ''
        ticker = yf.Ticker(f'{code}{suffix}')
        hist = ticker.history(period='2d')
        if hist.empty:
            return f'找不到股票代碼「{code}」'
        price = hist['Close'].iloc[-1]
        prev  = hist['Close'].iloc[-2] if len(hist) >= 2 else price
        chg   = price - prev
        pct   = chg / prev * 100
        arrow = '▲' if chg >= 0 else '▼'
        return f'📈 {code}\n現價：{price:.2f}\n{arrow} {abs(chg):.2f}（{abs(pct):.2f}%）'
    except Exception as e:
        return f'股價查詢失敗（{code}）：{str(e)}'

def check_alerts(line_bot_api):
    """檢查所有提醒，觸發時推播給設定的使用者"""
    alerts = load_alerts()
    triggered = []
    remaining = []

    for a in alerts:
        code = a['code']
        direction = a['direction']
        threshold = a['pct']
        user_id = a.get('user_id', '')

        try:
            import yfinance as yf
            suffix = '.TW' if (len(code) == 4 and code.isdigit()) else ''
            hist = yf.Ticker(f'{code}{suffix}').history(period='2d')
            if hist.empty or len(hist) < 2:
                remaining.append(a)
                continue
            price = hist['Close'].iloc[-1]
            prev  = hist['Close'].iloc[-2]
            pct   = (price - prev) / prev * 100

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
