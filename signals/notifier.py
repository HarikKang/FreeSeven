"""信号推送：钉钉机器人 / Server酱 / PushPlus"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import requests


def _dingtalk(title: str, content: str, webhook: str, secret: str) -> bool:
    """钉钉自定义机器人，支持加签。"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    sign = base64.b64encode(hmac_code).decode()
    url = f"{webhook}&{urlencode({'timestamp': timestamp, 'sign': sign})}"
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": content},
    }
    r = requests.post(url, json=payload, timeout=15)
    return r.status_code == 200 and r.json().get("errcode") == 0


def _serverchan(title: str, content: str, key: str) -> bool:
    r = requests.get(
        f"https://sctapi.ftqq.com/{key}.send",
        params={"title": title, "desp": content},
        timeout=15,
    )
    return r.status_code == 200 and r.json().get("code") == 0


def _pushplus(title: str, content: str, token: str) -> bool:
    r = requests.post(
        "https://www.pushplus.plus/send",
        json={"token": token, "title": title, "content": content},
        timeout=15,
    )
    return r.status_code == 200 and r.json().get("code") == 200


def notify(channel: str, title: str, content: str) -> bool:
    """按 channel 推送，返回是否成功。channel 空则只打印。"""
    if channel == "dingtalk":
        webhook = os.environ.get("DINGTALK_WEBHOOK_URL", "")
        secret = os.environ.get("DINGTALK_SECRET", "")
        if not webhook:
            print("[notify] 未配置 DINGTALK_WEBHOOK_URL，仅本地输出")
            return False
        return _dingtalk(title, content, webhook, secret)
    if channel == "serverchan":
        key = os.environ.get("SERVERCHAN_KEY", "")
        if not key:
            print("[notify] 未配置 SERVERCHAN_KEY，仅本地输出")
            return False
        return _serverchan(title, content, key)
    if channel == "pushplus":
        token = os.environ.get("PUSHPLUS_TOKEN", "")
        if not token:
            print("[notify] 未配置 PUSHPLUS_TOKEN，仅本地输出")
            return False
        return _pushplus(title, content, token)
    print(f"[notify] channel={channel} 未知，仅本地输出")
    return False