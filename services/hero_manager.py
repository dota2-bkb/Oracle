import json
import os
import pandas as pd
from typing import Dict, Any, List
from services.api_client import OpenDotaClient

DATA_DIR = "data"
SYSTEM_FILE = os.path.join(DATA_DIR, "heroes_system.json")
CUSTOM_FILE = os.path.join(DATA_DIR, "heroes_custom.json")

class HeroManager:
    def __init__(self):
        self._ensure_data_dir()
        self.heroes = {} # In-memory cache: {hero_id: hero_data_dict}
        self.load_heroes()

    def _ensure_data_dir(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

    def fetch_and_update_system_data(self) -> int:
        """
        从 OpenDota API 拉取最新数据，保存到 heroes_system.json
        """
        client = OpenDotaClient()
        data = client.fetch_heroes() # distinct from client.fetch_heroes() which returns list
        
        if not data:
            return 0

        # Convert list to dict keyed by ID for easier lookup
        heroes_dict = {}
        for item in data:
            # 处理图片 URL (OpenDota 经常给相对路径)
            img = item.get('img')
            if img and img.startswith('/'):
                img = f"https://cdn.cloudflare.steamstatic.com{img}"
            
            icon = item.get('icon')
            if icon and icon.startswith('/'):
                icon = f"https://cdn.cloudflare.steamstatic.com{icon}"

            heroes_dict[item['id']] = {
                "id": item['id'],
                "name": item.get('name'), # npc_dota_hero_...
                "en_name": item.get('localized_name'),
                "cn_name": "", # API 通常不给中文，需要后续补充或前端写死映射
                "slang": "",   # 用户自定义
                "img_url": img,
                "icon_url": icon,
                "primary_attr": item.get('primary_attr'),
                "roles": item.get('roles', [])
            }
        
        with open(SYSTEM_FILE, 'w', encoding='utf-8') as f:
            json.dump(heroes_dict, f, indent=2, ensure_ascii=False)
        
        # 如果没有 Custom 文件，就创建一个基于 System 的
        if not os.path.exists(CUSTOM_FILE):
            self._create_initial_custom_file(heroes_dict)
        
        self.load_heroes()
        return len(heroes_dict)

    def _create_initial_custom_file(self, system_data: Dict):
        """
        创建初始的 Custom 文件，只包含 id 和空的 cn_name/slang，避免冗余
        """
        custom_data = {}
        for hid, hdata in system_data.items():
            custom_data[hid] = {
                "id": hid,
                "en_name": hdata['en_name'], # 保留英文名方便对照
                "cn_name": hdata.get("cn_name", ""),
                "slang": ""
            }
        with open(CUSTOM_FILE, 'w', encoding='utf-8') as f:
            json.dump(custom_data, f, indent=2, ensure_ascii=False)

    def load_heroes(self):
        """
        加载逻辑：System 为主，Custom 覆盖特定字段
        """
        system_data = {}
        custom_data = {}

        if os.path.exists(SYSTEM_FILE):
            with open(SYSTEM_FILE, 'r', encoding='utf-8') as f:
                # JSON keys are always strings, but we want int keys for hero_id
                raw_sys = json.load(f)
                system_data = {int(k): v for k, v in raw_sys.items()}

        if os.path.exists(CUSTOM_FILE):
            with open(CUSTOM_FILE, 'r', encoding='utf-8') as f:
                raw_cust = json.load(f)
                custom_data = {int(k): v for k, v in raw_cust.items()}
        
        # Merge
        self.heroes = system_data.copy()
        for hid, cdata in custom_data.items():
            if hid in self.heroes:
                if cdata.get("cn_name"):
                    self.heroes[hid]["cn_name"] = cdata["cn_name"]
                if cdata.get("slang"):
                    self.heroes[hid]["slang"] = cdata["slang"]
    
    def get_hero(self, hero_id: int) -> Dict:
        return self.heroes.get(hero_id, {"en_name": f"Unknown ({hero_id})", "img_url": ""})

    def get_all_heroes(self) -> List[Dict]:
        return list(self.heroes.values())

    def export_csv(self) -> str:
        """
        导出用于编辑 Slang 的 CSV
        """
        # List of dicts
        data_list = []
        for hid, hdata in self.heroes.items():
            data_list.append({
                "hero_id": hid,
                "en_name": hdata.get("en_name"),
                "cn_name": hdata.get("cn_name", ""),
                "slang": hdata.get("slang", "")
            })
        
        df = pd.DataFrame(data_list)
        
        if df.empty:
            return ""

        # Sort by name (handling potential None values)
        # Convert to string to avoid type comparison errors if mixed
        df['en_name'] = df['en_name'].astype(str)
        df = df.sort_values("en_name")
        return df.to_csv(index=False)

    def import_csv(self, csv_file) -> bool:
        """
        从 CSV 导入并更新 Custom JSON
        """
        try:
            df = pd.read_csv(csv_file)
            
            # Validate columns
            required = ["hero_id", "cn_name", "slang"]
            for r in required:
                if r not in df.columns:
                    return False
            
            custom_data = {}
            # Load existing custom to preserve other potential fields
            if os.path.exists(CUSTOM_FILE):
                 with open(CUSTOM_FILE, 'r', encoding='utf-8') as f:
                    raw_cust = json.load(f)
                    custom_data = {int(k): v for k, v in raw_cust.items()}

            for _, row in df.iterrows():
                hid = int(row['hero_id'])
                if hid not in custom_data:
                    custom_data[hid] = {"id": hid}
                
                custom_data[hid]["cn_name"] = str(row["cn_name"]) if pd.notna(row["cn_name"]) else ""
                custom_data[hid]["slang"] = str(row["slang"]) if pd.notna(row["slang"]) else ""
            
            # Save back to Custom JSON
            with open(CUSTOM_FILE, 'w', encoding='utf-8') as f:
                json.dump(custom_data, f, indent=2, ensure_ascii=False)
            
            # Reload memory
            self.load_heroes()
            return True
        except Exception as e:
            print(f"CSV Import Error: {e}")
            return False

