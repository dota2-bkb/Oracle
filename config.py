# config.py

# OpenDota API Configuration
OPENDOTA_API_URL = "https://api.opendota.com/api"
# 如果有 API Key，可以在这里配置或者从环境变量读取
import os
from dotenv import load_dotenv

load_dotenv()

# 优先使用环境变量，否则使用硬编码的 Key (注意：不要将 Key 提交到公共仓库)
OPENDOTA_API_KEY = os.getenv("OPENDOTA_API_KEY", "")

# Hero Map (Sample, ideally this should be populated with all heroes)
# key: hero_id (int), value: dict
HERO_MAP = {
    1: {"en": "Anti-Mage", "cn": "敌法师", "slang": "AM/敌法"},
    2: {"en": "Axe", "cn": "斧王", "slang": "Axe/斧王"},
    # ... 可以在后续补充完整列表，或者通过 API 动态获取并缓存
}

# 常量定义
RADIANT_TEAM = 0 # Team side 0
DIRE_TEAM = 1    # Team side 1

