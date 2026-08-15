"""全局配置加载：config.yaml + .env"""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent


def _load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def load_config() -> dict:
    _load_dotenv(ROOT / "config" / ".env")
    with open(ROOT / "config" / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# import 即加载 .env，保证任意模块直接可用 token
_load_dotenv(ROOT / "config" / ".env")


def get_token() -> str:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token or token == "your_token_here":
        raise RuntimeError("未设置 TUSHARE_TOKEN，请在 config/.env 中配置")
    return token