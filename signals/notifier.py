"""信号推送：Server酱 / PushPlus"""
from __future__ import annotations

import os

import requests


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