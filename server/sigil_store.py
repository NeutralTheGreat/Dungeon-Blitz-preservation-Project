import struct
from bitreader import BitReader
from BitBuffer import BitBuffer
from globals import send_consumable_reward, send_charm_reward, send_mount_reward, send_dye_reward, send_gold_loss, send_new_pet_packet
from constants import get_mount_id
from accounts import save_characters
from constants import PET_TYPES

def handle_royal_sigil_store_purchase(session, data):
    """Handle Royal Sigil Store purchase requests (packet 0x106)"""
    br = BitReader(data[4:])
    
    # Read the item ID from the packet (5 bits as per class_12.const_753)
    item_id = br.read_method_20(5)
    
    print(f"[Royal Sigil Store] Purchase request from {session.addr}: item_id={item_id}")
    
    char = session.current_char_dict
    if not char:
        print("[Royal Sigil Store] No character data found")
        return
    
    # Royal Sigil Store items mapping (based on server data/RoyalStore data if it exists)
    # This is a basic implementation - adjust based on actual game data
    store_items = {
        0: {"name": "MountLockbox01L01", "type": "mount", "cost_sigils": 100, "cost_gold": 0},
        1: {"name": "Lockbox01L01", "type": "pet", "cost_sigils": 75, "cost_gold": 0},
        2: {"name": "RarePetFood", "type": "consumable", "cost_sigils": 25, "cost_gold": 0},
        3: {"name": "RespecStone", "type": "charm", "cost_sigils": 50, "cost_gold": 0},
        4: {"name": "CharmRemover", "type": "charm", "cost_sigils": 30, "cost_gold": 0},
        # Add more items as needed based on your game's Royal Sigil Store configuration
    }
    
    if item_id not in store_items:
        print(f"[Royal Sigil Store] Unknown item ID: {item_id}")
        return
    
    item = store_items[item_id]
    item_name = item["name"]
    item_type = item["type"]
    cost_sigils = item.get("cost_sigils", 0)
    cost_gold = item.get("cost_gold", 0)
    
    # Check if player has enough currency
    current_sigils = int(char.get("SilverSigils", 0))  # Note: Using SilverSigils as per template data
    current_gold = int(char.get("gold", 0))  # Cast to int
    
    if cost_sigils > 0 and current_sigils < cost_sigils:
        print(f"[Royal Sigil Store] Insufficient sigils: has {current_sigils}, needs {cost_sigils}")
        return
    
    if cost_gold > 0 and current_gold < cost_gold:
        print(f"[Royal Sigil Store] Insufficient gold: has {current_gold}, needs {cost_gold}")
        return
    
    # Deduct currency
    save_needed = False
    
    if cost_sigils > 0:
        char["SilverSigils"] -= cost_sigils
        # Send sigil decrease packet (0x10f)
        bb = BitBuffer()
        bb.write_method_4(cost_sigils)
        payload = bb.to_bytes()
        pkt = struct.pack(">HH", 0x10f, len(payload)) + payload
        session.conn.sendall(pkt)
        save_needed = True
        print(f"[Royal Sigil Store] Deducted {cost_sigils} sigils, remaining: {char['SilverSigils']}")
    
    if cost_gold > 0:
        char["gold"] -= cost_gold
        from globals import send_gold_loss
        send_gold_loss(session, cost_gold)
        save_needed = True
        print(f"[Royal Sigil Store] Deducted {cost_gold} gold")
    
    # Grant the purchased item
    if item_type == "mount":
        mount_id = get_mount_id(item_name)
        if mount_id != 0:
            mounts = char.setdefault("mounts", [])
            if mount_id not in mounts:
                mounts.append(mount_id)
                send_mount_reward(session, mount_id)
                save_needed = True
                print(f"[Royal Sigil Store] {char['name']} purchased mount {item_name} (ID: {mount_id})")
        else:
            print(f"[Royal Sigil Store] Warning: Unknown mount ID for {item_name}")
    
    elif item_type == "pet":
        # Add pet to owned pets (level 1)
        # Find pet definition
        pet_def = next((p for p in PET_TYPES if p.get("PetName") == item_name or p.get("PetID") == item_name), None)
        if pet_def:
            pet_type_id = pet_def["PetID"]
            starting_rank = 1
            
            pets = char.get("pets", [])
            special_id = max((p.get("special_id", 0) for p in pets), default=0) + 1
            
            new_pet = {
                "typeID": pet_type_id,
                "special_id": special_id,
                "level": starting_rank,
                "xp": 0,
            }
            
            pets.append(new_pet)
            char["pets"] = pets
            
            send_new_pet_packet(session, pet_type_id, special_id, starting_rank)
            save_needed = True
            print(f"[Royal Sigil Store] {char['name']} purchased pet {item_name}")

    
    elif item_type == "consumable":
        consumables = char.setdefault("consumables", [])
        found = False
        for entry in consumables:
            if entry.get("consumableName") == item_name:
                entry["count"] = int(entry.get("count", 0)) + 1
                found = True
                break
        if not found:
            consumables.append({"consumableName": item_name, "count": 1})
        send_consumable_reward(session, item_name, 1)
        save_needed = True
        print(f"[Royal Sigil Store] {char['name']} purchased {item_name}")
    
    elif item_type == "charm":
        charms = char.setdefault("charms", [])
        found = False
        for entry in charms:
            if entry.get("charmName") == item_name:
                entry["count"] = int(entry.get("count", 0)) + 1
                found = True
                break
        if not found:
            charms.append({"charmName": item_name, "count": 1})
        send_charm_reward(session, item_name)
        save_needed = True
        print(f"[Royal Sigil Store] {char['name']} purchased charm {item_name}")
    
    if save_needed:
        save_characters(session.user_id, session.char_list)
