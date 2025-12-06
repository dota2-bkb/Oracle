import os
import sys

# Add project root to path to allow imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from services.patch_manager import PatchManager

def main():
    print("Initializing Patch Manager...")
    pm = PatchManager()
    
    print("Fetching updates from OpenDota API...")
    try:
        count = pm.update_from_api()
        print(f"Success! Updated {count} patches.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
