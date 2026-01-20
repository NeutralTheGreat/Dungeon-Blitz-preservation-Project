
import json
import os

TARGET_FILE = "server/world_npcs/GoblinRiverDungeon.json"

def transform_npc(npc):
    # Enforce standard keys based on JadeCity.json
    new_npc = {
        "id": npc.get("id"),
        "name": npc.get("name", ""),
        "x": npc.get("x", 0),
        "y": npc.get("y", 0),
        "v": npc.get("v", 0),
        "team": npc.get("team", 2),
        "untargetable": npc.get("untargetable", False),
        "render_depth_offset": npc.get("render_depth_offset", 0),
        "character_name": npc.get("character_name", ""),
        "DramaAnim": npc.get("DramaAnim", ""),
        "SleepAnim": npc.get("SleepAnim", ""),
        "Linked_Mission": npc.get("Linked_Mission", ""),
        "summonerId": npc.get("summonerId", 0),
        "power_id": npc.get("power_id", 0),
        "entState": npc.get("entState", 1),
        "facing_left": npc.get("facing_left", True),
        "health_delta": npc.get("health_delta", 0),
        "buffs": npc.get("buffs", [])
    }
    return new_npc

def main():
    if not os.path.exists(TARGET_FILE):
        print(f"File {TARGET_FILE} not found!")
        return

    with open(TARGET_FILE, "r") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} NPCs from {TARGET_FILE}")

    # Renumber IDs to avoid collision with Player (low IDs)
    start_id = 900000
    
    new_data = []
    for i, npc in enumerate(data):
        new_npc = transform_npc(npc)
        new_npc["id"] = start_id + i
        new_npc["summonerId"] = 0 # Force 0 to avoid minion logic
        new_data.append(new_npc)

    with open(TARGET_FILE, "w") as f:
        json.dump(new_data, f, indent=4)

    print(f"Transformed and saved {len(new_data)} NPCs to {TARGET_FILE}")

if __name__ == "__main__":
    main()
