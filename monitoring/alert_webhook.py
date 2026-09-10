import json
import logging
import os
import sys
from datetime import datetime
from flask import Flask,request
import requests


app=Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger=logging.getLogger("alert-webhook")

DINGTALK_WEBHOOK=os.environ.get("DINGTALK_WEBHOOK","").strip()
if not DINGTALK_WEBHOOK:
    logger.error("环境变量 DINGTALK_WEBHOOK 未设置，无法发送钉钉告警，启动失败")
    sys.exit(1)

DINGTALK_SECRET=os.environ.get("DINGTALK_SECRET","")

SEVERITY_EMOJI={
        "critical":"🔴",
        "warning":"🟡",
        "info":"🟢"
        }


_AT_CRITICAL=os.environ.get("AT_CRITICAL_MOBILES","")
SEVERITY_AT={
        "critical":[m.strip() for m in _AT_CRITICAL.split(",") if m.strip()],
        "warning":[],
        "info":[]
        }

def send_dingtalk(title:str,text:str,at_mobiles:list=None):
    """发送钉钉机器人消息"""
    payload={
            "msgtype":"markdown",
            "markdown":{
                "title":title,
                "text":text
                },
            "at":{
                "atMobiles":at_mobiles or [],
                "isAtAll":False
                }
            }
    try:
        resp=requests.post(
                DINGTALK_WEBHOOK,
                json=payload,
                timeout=10,
                headers={"Content-Type":"application/json"}
                )
        resp.raise_for_status()
        logger.info(f"DingTalk sent:{resp.json()}")
        return True
    except Exception as e:
        logger.error(f"DingTalk send failed :{e}")
        return False

def format_alert(alert:dict):
    """格式化单个告警为markdown"""
    status=alert.get("status","firing")
    labels=alert.get("labels",{})
    annotations=alert.get("annotations",{})
    severity=labels.get("severity","warning")

    emoji=SEVERITY_EMOJI.get(severity,"⚪")
    status_emoji="已恢复" if status =="resolved" else f"{emoji} 告警触发"

    lines=[
            f"###{status_emoji} {labels.get('alertname','Unknown')}",
            f"",
        f"- **级别**: {severity.upper()}",
        f"- **服务**: {labels.get('job', 'unknown')}",
        f"- **实例**: {labels.get('instance', 'unknown')}",
        f"- **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"**摘要**: {annotations.get('summary', 'N/A')}",
        f"",
        f"**详情**: {annotations.get('description', 'N/A')}",
        f"---"
    ]
    return "\n".join(lines)

@app.route("/webhook/dingtalk",methods=["POST"])
def dingtalk_webhook():
    """接受Alertmanager的webhhok"""
    data=request.get_json() or {}
    alerts=data.get("alerts",[])
    if not alerts:
        return {"status":"ignored","reason":"no alerts"},200
    max_severity="info"
    formatted_alerts=[]
    for alert in alerts:
        formatted_alerts.append(format_alert(alert))
        sev=alert.get("labels",{}).get("severity","info")
        if sev=="critical":
            max_severity="critical"
        elif sev=="warning" and max_severity !="critical":
            max_severity="warning"

    title=f"[weibo监控]{len(alerts)}条告警"
    content="\n".join(formatted_alerts)

    if len(content)>15000:
        content=content[:15000]+"\n\n.....(内容过长已截断)"
    at_mobiles=SEVERITY_AT.get(max_severity,[])
    success=send_dingtalk(title,content,at_mobiles)
    return {"status":"ok" if success else "failed"},200




@app.route("/health")
def health():
    return {"status":"ok"},200

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5001,debug=False)


                
