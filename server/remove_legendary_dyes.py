#!/usr/bin/env python3
"""Remove all legendary dyes from player save file (OwnedDyes and dyes lists)."""
import json
import os

LEGENDARY_DYE_IDS = {
    1, 9, 10, 18, 24, 29, 33, 34, 44, 51, 66, 67, 85, 99, 136, 143, 181, 205, 211, 247,
}

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, "saves", "1.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for char in data.get("characters", []):
        name = char.get("name", "Unknown")
        owned = char.get("OwnedDyes", [])
        before = len(owned)
        char["OwnedDyes"] = [d for d in owned if d not in LEGENDARY_DYE_IDS]
        removed = before - len(char["OwnedDyes"])
        char["dyes"] = []
        if removed:
            print(f"{name}: {removed} efsanevi boya kaldirildi ({before} -> {len(char['OwnedDyes'])})")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("Kaydedildi:", path)

if __name__ == "__main__":
    main()
