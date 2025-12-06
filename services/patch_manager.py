import json
import os
import requests
from typing import Dict, List, Optional
from datetime import datetime

DATA_DIR = "data"
PATCH_FILE = os.path.join(DATA_DIR, "patches.json")
API_URL = "https://api.opendota.com/api/constants/patch"

class PatchManager:
    def __init__(self):
        self._ensure_file()
        self.patches = self._load_patches()

    def _ensure_file(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if not os.path.exists(PATCH_FILE):
            # Default patches (sample)
            defaults = {
                "7.37d": {"start_date": "2024-10-01"}, # Example date
                "7.37c": {"start_date": "2024-09-01"},
                "7.37":  {"start_date": "2024-05-22"}
            }
            with open(PATCH_FILE, 'w', encoding='utf-8') as f:
                json.dump(defaults, f, indent=2)

    def _load_patches(self) -> Dict:
        try:
            with open(PATCH_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}

    def save_patch(self, name: str, start_date_str: str):
        self.patches[name] = {"start_date": start_date_str}
        with open(PATCH_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.patches, f, indent=2)

    def get_all_patches(self) -> List[str]:
        # Sort by date desc
        sorted_patches = sorted(
            self.patches.items(), 
            key=lambda x: x[1]['start_date'], 
            reverse=True
        )
        return [k for k, v in sorted_patches]

    def get_patch_date(self, patch_name: str) -> Optional[datetime]:
        p = self.patches.get(patch_name)
        if p:
            return datetime.strptime(p['start_date'], "%Y-%m-%d").date()
        return None

    def update_from_api(self) -> int:
        """
        Fetch patches from OpenDota and update local file.
        Returns number of new/updated patches.
        """
        try:
            resp = requests.get(API_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise Exception(f"API Request failed: {e}")

        count = 0
        for item in data:
            name = item.get('name')
            date_str = item.get('date')
            
            if not name or not date_str:
                continue
                
            try:
                # OpenDota date: 2024-10-02T00:00:00.000Z
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_fmt = dt.strftime("%Y-%m-%d")
                
                # Check if update needed
                if name not in self.patches or self.patches[name]['start_date'] != date_fmt:
                    self.patches[name] = {"start_date": date_fmt}
                    count += 1
            except:
                continue
        
        if count > 0:
            with open(PATCH_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.patches, f, indent=2, ensure_ascii=False)
                
        return count
