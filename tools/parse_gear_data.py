import re
import json
import os

SWZ_PATH = "extra-modules/swz-scripts/Login.swz.txt"
OUTPUT_PATH = "server/data/gear_data.json"

def parse_gear_data():
    if not os.path.exists(SWZ_PATH):
        print(f"Error: {SWZ_PATH} not found.")
        return

    print(f"Reading {SWZ_PATH}...")
    with open(SWZ_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex to find Gear blocks
    # <Gear GearName="AxeStarter1" GearID="1" Type="Sword"> ... </Gear>
    # We need to extract fields inside.
    
    gear_pattern = re.compile(r'<Gear\s+GearName="([^"]+)"\s+GearID="(\d+)"\s+Type="([^"]+)">\s*(.*?)\s*</Gear>', re.DOTALL)
    
    gears = {}
    
    matches = gear_pattern.findall(content)
    print(f"Found {len(matches)} gear entries.")
    
    for name, gear_id, gear_type, body in matches:
        gear_id = int(gear_id)
        if gear_id == 0:
            continue
            
        entry = {
            "name": name,
            "id": gear_id,
            "type": gear_type,
            "realm": None,
            "boss": None,
            "rarity": "M" # Default to Common/Magic
        }
        
        # Extract nested fields
        realm_match = re.search(r'<Realm>([^<]+)</Realm>', body)
        if realm_match:
            entry["realm"] = realm_match.group(1)
            
        boss_match = re.search(r'<BossName>([^<]+)</BossName>', body)
        if boss_match:
            entry["boss"] = boss_match.group(1)
        
        rarity_match = re.search(r'<Rarity>([^<]+)</Rarity>', body)
        if rarity_match:
            entry["rarity"] = rarity_match.group(1)
        
        # We want to group by ID or just have a lookup?
        # A gear ID might have multiple variants (R, L) but they usually share the ID in the XML?
        # Wait, the XML shows different GearNames sharing the same GearID!
        # Example: AxeStarter1 (ID 1), AxeStarter1R (ID 1), AxeStarter1L (ID 1).
        # They differ by Rarity (M, R, L) and potentially Realm (AxeStarter1 has no Realm? AxeStarter1R has Ghost).
        # This is interesting. The ID is the same, but the item variant differs.
        # The game likely uses ID + Rarity + (maybe) Tier/Level to determine the item.
        # BUT, if we are dropping an item, we pick an ID first.
        # The prompt says: "check out which item drops on who/which map".
        # If I drop ID 1, do I drop the Common, Rare, or Legendary version?
        # The `calculate_drop_data` handles the Tier (Rarity).
        # So I need to map Realm/Boss -> List of valid Gear IDs.
        
        # Let's store all variants for now to see the data structure.
        if gear_id not in gears:
            gears[gear_id] = []
        gears[gear_id].append(entry)

    # Re-organize for easy lookup:
    # 1. Map: Realm -> [Gear IDs]
    # 2. Map: Boss -> [Gear IDs]
    # 3. Map: Global -> [Gear IDs] (No Realm/Boss)
    
    realm_drops = {}
    boss_drops = {}
    global_drops = []
    
    for gid, variants in gears.items():
        # Check if ALL variants have same realm/boss or if it differs.
        # Usually drops are tied to the base item or specific rarities drop in specific places?
        # Example: AxeStarter1 (Common) - No Realm. AxeStarter1R (Rare) - Realm Ghost.
        # This implies: Common version drops globally? Rare version drops in Ghost realm?
        # Or maybe the "Realm" tag implies where it drops *primarily*.
        
        # Let's aggregate unique realms/bosses for this ID.
        realms = set()
        bosses = set()
        has_global_variant = False
        
        for v in variants:
            if v["realm"]: realms.add(v["realm"])
            if v["boss"]: bosses.add(v["boss"])
            if not v["realm"] and not v["boss"]: has_global_variant = True
            
        # If an item has specific drops, we should use them.
        for r in realms:
            if r not in realm_drops: realm_drops[r] = []
            if gid not in realm_drops[r]: realm_drops[r].append(gid)
            
        for b in bosses:
            if b not in boss_drops: boss_drops[b] = []
            if gid not in boss_drops[b]: boss_drops[b].append(gid)
            
        if has_global_variant:
             if gid not in global_drops: global_drops.append(gid)
    
    output_data = {
        "realm_drops": realm_drops,
        "boss_drops": boss_drops,
        "global_drops": global_drops,
        "all_gear_details": gears
    }
    
    print(f"Saving to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4)
    print("Done.")

if __name__ == "__main__":
    parse_gear_data()
