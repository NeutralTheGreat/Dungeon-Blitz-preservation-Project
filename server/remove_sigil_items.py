#!/usr/bin/env python3
"""Remove sigil market owned items (mounts + pets) from player save."""
import json
import os
import shutil

SIGIL_MOUNT_IDS = {106, 107, 108}
SIGIL_PET_IDS = {65, 66, 67, 68, 69, 70}


def run(save_path: str, backup: bool = True) -> None:
    if backup:
        bp = save_path.replace(".json", ".sigil_backup.json")
        shutil.copy2(save_path, bp)
        print("Yedek:", bp)

    with open(save_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for char in data.get("characters", []):
        mounts = char.get("mounts", [])
        before_m = len(mounts)
        char["mounts"] = [m for m in mounts if m not in SIGIL_MOUNT_IDS]

        pets = char.get("pets", [])
        before_p = len(pets)
        char["pets"] = [p for p in pets if p.get("typeID") not in SIGIL_PET_IDS]

        dm = before_m - len(char["mounts"])
        dp = before_p - len(char["pets"])
        if dm or dp:
            print(f"{char.get('name')}: sigil mount -{dm} | sigil pet -{dp}")

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("Kaydedildi:", os.path.abspath(save_path))


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    run(os.path.join(script_dir, "saves", "2.json"), backup=True)
