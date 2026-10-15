"""Chinese notification presentation for both retained and newly created messages."""

import re

TRANSLATIONS = {
    "operational state changed to normal. Existing activity is retained.": "設備狀態已變更為正常，既有使用、排隊與預約紀錄均保留。",
    "operational state changed to maintenance. Existing activity is retained.": "設備狀態已變更為維護中，既有使用、排隊與預約紀錄均保留。",
    "operational state changed to out_of_service. Existing activity is retained.": "設備狀態已變更為停用，既有使用、排隊與預約紀錄均保留。",
    "Your queue offer expired without a Claim. You may join the back of the queue again.": "排隊通知已逾期，尚未 Claim。你可以重新加入隊伍末端。",
    "Your reservation became no-show after the 15-minute check-in deadline.": "預約已超過 15 分鐘報到期限，系統已記錄為未到場。",
    "your usage estimate is overdue. Record Release when finished; no automatic release occurs.": "已超過預計使用時間。完成後請手動 Release，系統不會自動釋放設備。",
    "your reservation has started. Check in or manually Claim within the displayed attendance deadline; checked-in priority lasts until the booked end. Attendance never creates usage automatically.": "你的預約已開始，請在報到期限內報到或手動 Claim。報到後保留優先權至預約結束；報到不會自動開始使用。",
    "a reservation has started while you remain recorded as using it. Coordinate a manual Release.": "下一筆預約已開始，但你仍在使用中，請協調並手動 Release。",
    "your reservation has priority. Manually Claim to start usage.": "你的預約具有優先權，請手動 Claim 開始使用。",
    "it is your turn. Manually Claim within 15 minutes; notification is not usage.": "輪到你了！請在 15 分鐘內手動 Claim；收到通知不代表已開始使用。",
    " Upcoming reservation: ": " 下一筆預約：",
    "; plan a manual handoff before it starts.": "；請在預約開始前協調交接。",
    "your queue offer resumed with its remaining response time. Manually Claim before the displayed deadline.": "排隊通知已恢復，保留剩餘回應時間，請在顯示的期限前手動 Claim。",
    "usage was recorded as released.": "已記錄使用結束，設備已 Release。",
    "your queue entry was removed by an explicit action.": "你的排隊紀錄已被移除。",
    "upcoming reservation scheduled for ": "已安排預約，開始時間：",
    ". Manually check in or Claim when it starts.": "。預約開始後請手動報到或 Claim。",
    "an upcoming reservation at ": "下一筆預約將於 ",
    " overlaps your estimated usage. Coordinate a manual Release.": " 開始，與你的預計使用時間重疊，請協調並手動 Release。",
    "reservation holder checked in and awaits a manual recorded Release.": "預約者已報到，正在等待目前使用者手動 Release。",
}


def chinese_message(message):
    # Equipment names are user data, not translatable interface text.
    match = re.match(r"^(.*?)(: |：)(.*)$", message, re.DOTALL)
    prefix = match[1] + match[2] if match else ""
    message = match[3] if match else message
    for source, translated in TRANSLATIONS.items():
        message = message.replace(source, translated)
    return prefix + (
        message.replace(" Asia/Taipei", "")
        .replace("預約開始後請手動報到或 Claim", "設備可用並通知後，請在期限內按 Start using")
        .replace("Claim", "Start using")
    )
