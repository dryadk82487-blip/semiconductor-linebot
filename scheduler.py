import schedule, time, threading
from financial import get_summary
from stocks import check_alerts

def start_scheduler(line_bot_api, admin_user_id):
    def job_weekly_summary():
        if not admin_user_id:
            return
        msg = get_summary()
        from linebot.models import TextSendMessage
        try:
            line_bot_api.push_message(admin_user_id, TextSendMessage(text=msg))
        except Exception as e:
            print(f'推播週報失敗: {e}')

    def job_check_alerts():
        check_alerts(line_bot_api)

    # 每週一早上 8:00 推送週報
    schedule.every().monday.at('08:00').do(job_weekly_summary)
    # 每小時整點檢查股票提醒
    schedule.every().hour.do(job_check_alerts)

    def run():
        while True:
            schedule.run_pending()
            time.sleep(60)

    t = threading.Thread(target=run, daemon=True)
    t.start()
