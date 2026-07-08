import os, json, re, threading, time
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from financial import query_financial, get_summary
from stocks import get_stock_price, load_alerts, save_alerts, check_alerts
from scheduler import start_scheduler

app = Flask(__name__)

CHANNEL_SECRET       = os.environ['LINE_CHANNEL_SECRET']
CHANNEL_ACCESS_TOKEN = os.environ['LINE_CHANNEL_ACCESS_TOKEN']
CLAUDE_API_KEY       = os.environ.get('CLAUDE_API_KEY', '')
ADMIN_USER_ID        = os.environ.get('ADMIN_USER_ID', '')  # 你的 LINE userId，用於推播

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 啟動排程（背景執行緒）
start_scheduler(line_bot_api, ADMIN_USER_ID)


@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200


@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK', 200


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    reply = process(text, user_id)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))


def process(text, user_id):
    t = text.strip()

    # ── 幫助 ──────────────────────────────────────────
    if t in ['幫助', 'help', '?', '？', '功能']:
        return HELP_TEXT

    # ── 查財報：「查VIS」「查 UMC」 ───────────────────
    if t.startswith('查'):
        name = t[1:].strip()
        return query_financial(name)

    # ── 查股價：「股價2330」 ──────────────────────────
    if t.startswith('股價'):
        code = t[2:].strip()
        return get_stock_price(code)

    # ── 設定提醒：「提醒 2330 漲5%」「提醒 2330 跌3%」 ─
    m = re.match(r'^提醒\s*(\S+)\s*(漲|跌)\s*(\d+\.?\d*)%$', t)
    if m:
        code, direction, pct = m.group(1), m.group(2), float(m.group(3))
        alerts = load_alerts()
        alerts.append({'code': code, 'direction': direction, 'pct': pct, 'user_id': user_id})
        save_alerts(alerts)
        return f'✅ 已設定：{code} {direction}{pct}% 時通知你'

    # ── 查提醒清單 ──────────────────────────────────
    if t in ['我的提醒', '提醒清單']:
        alerts = [a for a in load_alerts() if a.get('user_id') == user_id]
        if not alerts:
            return '你目前沒有設定任何股票提醒'
        lines = ['📋 你的提醒清單：']
        for a in alerts:
            lines.append(f"  {a['code']} {a['direction']}{a['pct']}%")
        return '\n'.join(lines)

    # ── 刪除提醒 ──────────────────────────────────
    if t.startswith('刪除提醒'):
        code = t.replace('刪除提醒', '').strip()
        alerts = load_alerts()
        before = len(alerts)
        alerts = [a for a in alerts if not (a['code'] == code and a.get('user_id') == user_id)]
        save_alerts(alerts)
        removed = before - len(alerts)
        return f'✅ 已刪除 {code} 的提醒 ({removed} 筆)' if removed else f'找不到 {code} 的提醒'

    # ── 本週摘要 ──────────────────────────────────
    if t in ['摘要', '本週摘要', '市場摘要']:
        return get_summary()

    # ── AI 問答 ──────────────────────────────────
    if CLAUDE_API_KEY:
        return ask_claude(t, CLAUDE_API_KEY)

    return '請輸入「幫助」查看所有功能 🤖'


def ask_claude(text, api_key):
    import requests as req
    from financial import load_data
    data = load_data()
    # 只傳最近一季給 Claude 以縮短 prompt
    brief = [{
        'name': c['name'], 'market': c['market'],
        'lastQ': c['quarters'][-1] if c['quarters'] else '',
        'revenue': c['revenue'][-1] if c['revenue'] else None,
        'gm': c['grossMargin'][-1] if c['grossMargin'] else None,
        'eps': c['eps'][-1] if c['eps'] else None,
    } for c in data]
    context = json.dumps(brief, ensure_ascii=False)

    headers = {
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
    }
    body = {
        'model': 'claude-haiku-4-5-20251001',
        'max_tokens': 400,
        'messages': [{
            'role': 'user',
            'content': (
                '你是半導體財報助理，只用繁體中文回答，回答要簡短（150字以內）。\n'
                f'財報資料（最新一季）：{context}\n\n問題：{text}'
            )
        }]
    }
    try:
        r = req.post('https://api.anthropic.com/v1/messages', headers=headers, json=body, timeout=15)
        if r.ok:
            return r.json()['content'][0]['text']
        return 'AI 暫時無法回應，請稍後再試'
    except Exception:
        return 'AI 連線逾時，請稍後再試'


HELP_TEXT = """🤖 半導體財報助理

📊 查財報（最近4季）
  → 查VIS  查UMC  查ADI

📈 查即時股價
  → 股價2330  股價2454

🔔 設定漲跌提醒
  → 提醒 2330 漲5%
  → 提醒 2303 跌3%
  → 我的提醒
  → 刪除提醒 2330

📅 週報摘要
  → 摘要

💬 AI 問答（需設定 API Key）
  → 直接輸入問題即可"""
