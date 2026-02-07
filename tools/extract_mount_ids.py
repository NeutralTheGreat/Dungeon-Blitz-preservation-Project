import re
import json
import os

SWZ_PATH = r"c:\Users\ArdaPC\Documents\GitHub\dungeon-blitz-flash-reboot\extra-modules\swz-scripts\Game.swz.txt"
OUTPUT_PATH = r"c:\Users\ArdaPC\Documents\GitHub\dungeon-blitz-flash-reboot\server\data\mount_ids.json"

def extract_mounts():
    if not os.path.exists(SWZ_PATH):
        print(f"Error: {SWZ_PATH} not found")
        return

    mounts = {}
    with open(SWZ_PATH, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Regex to find MountType blocks
    # <MountType MountName="MountLockbox01L01"> ... <MountID>106</MountID>
    pattern = re.compile(r'<MountType MountName="([^"]+)">\s*<MountID>(\d+)</MountID>', re.DOTALL)
    
    matches = pattern.findall(content)
    print(f"Found {len(matches)} mounts")
    
    for name, mid in matches:
        mounts[name] = int(mid)
        
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(mounts, f, indent=4)
    print(f"Saved to {OUTPUT_PATH}")
    
    # helper: print for verification
    if "MountLockbox01L01" in mounts:
        print(f"MountLockbox01L01 -> {mounts['MountLockbox01L01']}")

if __name__ == "__main__":
    extract_mounts()
