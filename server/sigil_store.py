import struct
from bitreader import BitReader
from BitBuffer import BitBuffer
from game_data import get_random_gear_id
from globals import send_consumable_reward, send_charm_reward, send_mount_reward, send_dye_reward, send_gold_loss, send_new_pet_packet, send_gear_reward
from accounts import save_characters
from constants import get_mount_id, PET_TYPES

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
    
    # Royal Sigil Store items mapping (based on Game.swz.txt RoyalStoreTypes XML)
    # IDs match client-side RoyalStoreID values
    store_items = {
        # Special items (mounts/pets) - IDs 1-7
        1: {"name": "MountLockbox01L02", "type": "mount", "cost_sigils": 3200, "quantity": 1},  # Hatebreed Charger
        2: {"name": "MountLockbox01R01", "type": "mount", "cost_sigils": 640, "quantity": 1},   # Stormhoof Stallion
        3: {"name": "Lockbox01L02", "type": "pet", "cost_sigils": 2400, "quantity": 1},         # Darkheart Apparition
        4: {"name": "Lockbox01RRed", "type": "pet", "cost_sigils": 320, "quantity": 1},         # Accursed Counselor
        5: {"name": "Lockbox01RYellow", "type": "pet", "cost_sigils": 320, "quantity": 1},      # Ruined Counselor
        6: {"name": "Lockbox01RBlue", "type": "pet", "cost_sigils": 320, "quantity": 1},        # Hexed Counselor
        7: {"name": "Lockbox01RGreen", "type": "pet", "cost_sigils": 320, "quantity": 1},       # Doomed Counselor
        
        # Potions & Special Items - IDs 8-15 (visible in screenshot)
        8: {"name": "RespecStone", "type": "respec_stone", "cost_sigils": 320, "quantity": 1},      # Respec Stone (special type)
        9: {"name": "XPFindRegular", "type": "consumable", "cost_sigils": 16, "quantity": 3},        # Potion of XP Boost x3
        10: {"name": "MaterialFindRegular", "type": "consumable", "cost_sigils": 16, "quantity": 3}, # Potion of Material Find x3
        11: {"name": "GoldFindRegular", "type": "consumable", "cost_sigils": 16, "quantity": 3},     # Potion of Gold Find x3
        12: {"name": "GearFindRegular", "type": "consumable", "cost_sigils": 16, "quantity": 3},     # Potion of Gear Find x3
        13: {"name": "Resurrection", "type": "consumable", "cost_sigils": 32, "quantity": 5},        # Vengeance Potion x5
        14: {"name": "ForgeXP", "type": "consumable", "cost_sigils": 112, "quantity": 1},            # Tinkerer's Soul
        15: {"name": "CharmRemover", "type": "charm_remover", "cost_sigils": 80, "quantity": 1},     # Charm Remover (special type)
    }
    
    if item_id not in store_items:
        print(f"[Royal Sigil Store] Unknown item ID: {item_id}")
        return
    
    item = store_items[item_id]
    item_name = item["name"]
    item_type = item["type"]
    cost_sigils = item.get("cost_sigils", 0)
    cost_gold = item.get("cost_gold", 0)
    quantity = item.get("quantity", 1)  # How many items to grant
    
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
        from constants import get_consumable_id
        consumable_id = get_consumable_id(item_name)
        print(f"[Royal Sigil Store DEBUG] item_name='{item_name}' -> consumable_id={consumable_id}")
        if consumable_id == 0:
            print(f"[Royal Sigil Store] Warning: Unknown consumable '{item_name}'")
        else:
            consumables = char.setdefault("consumables", [])
            print(f"[Royal Sigil Store DEBUG] Current consumables before: {consumables}")
            found = False
            new_total = 0
            for entry in consumables:
                if entry.get("consumableID") == consumable_id:
                    entry["count"] = int(entry.get("count", 0)) + quantity
                    new_total = entry["count"]
                    found = True
                    break
            if not found:
                consumables.append({"consumableID": consumable_id, "count": quantity})
                new_total = quantity
            print(f"[Royal Sigil Store DEBUG] Current consumables after: {consumables}")
            print(f"[Royal Sigil Store DEBUG] Calling send_consumable_reward(session, '{item_name}', {quantity}, {new_total})")
            send_consumable_reward(session, item_name, quantity, new_total)
            save_needed = True
            print(f"[Royal Sigil Store] {char['name']} purchased {item_name} (ID:{consumable_id}) x{quantity}, total: {new_total}")
    
    elif item_type == "charm":
        from constants import get_charm_id
        charm_id = get_charm_id(item_name)
        if charm_id == 0:
            print(f"[Royal Sigil Store] Warning: Unknown charm '{item_name}'")
        else:
            charms = char.setdefault("charms", [])
            found = False
            for entry in charms:
                if entry.get("charmID") == charm_id:
                    entry["count"] = int(entry.get("count", 0)) + quantity
                    found = True
                    break
            if not found:
                charms.append({"charmID": charm_id, "count": quantity})
            send_charm_reward(session, item_name)
            save_needed = True
            print(f"[Royal Sigil Store] {char['name']} purchased charm {item_name} (ID:{charm_id}) x{quantity}")

    elif item_type == "respec_stone":
        # RespecStone is a special charm-like item
        from constants import get_charm_id
        charm_id = get_charm_id(item_name)
        if charm_id == 0:
            print(f"[Royal Sigil Store] Warning: Unknown respec stone '{item_name}'")
        else:
            charms = char.setdefault("charms", [])
            found = False
            for entry in charms:
                if entry.get("charmID") == charm_id:
                    entry["count"] = int(entry.get("count", 0)) + quantity
                    found = True
                    break
            if not found:
                charms.append({"charmID": charm_id, "count": quantity})
            send_charm_reward(session, item_name)
            save_needed = True
            print(f"[Royal Sigil Store] {char['name']} purchased Respec Stone (ID:{charm_id}) x{quantity}")

    elif item_type == "charm_remover":
        # CharmRemover is a special charm-like item
        from constants import get_charm_id
        charm_id = get_charm_id(item_name)
        if charm_id == 0:
            print(f"[Royal Sigil Store] Warning: Unknown charm remover '{item_name}'")
        else:
            charms = char.setdefault("charms", [])
            found = False
            for entry in charms:
                if entry.get("charmID") == charm_id:
                    entry["count"] = int(entry.get("count", 0)) + quantity
                    found = True
                    break
            if not found:
                charms.append({"charmID": charm_id, "count": quantity})
            send_charm_reward(session, item_name)
            save_needed = True
            print(f"[Royal Sigil Store] {char['name']} purchased Charm Remover (ID:{charm_id}) x{quantity}")

    elif item_type == "gear":
        # Grant random gear matching the category/name
        # Need to determine gear level/stats based on player level? Or just give default.
        # get_random_gear_id(category_name)
        gear_id = get_random_gear_id(item_name) # Assuming item_name is the category
        if gear_id != 0:
            # Add to inventory? 
            # Usually send_gear_reward handles sending the packet, but we also need to SAVE it.
            # Server-side gear persistence is complex (needs unique ID allocation etc.)
            # For now, just send the reward packet so client sees it. 
            # Persistence requires 'inventory' structure update.
            # TODO: Add gear persistence properly.
            
            # For now, just send visual.
            send_gear_reward(session, gear_id)
            save_needed = True # Just to be safe
            print(f"[Royal Sigil Store] {char['name']} purchased gear {item_name} -> {gear_id}")
        else:
             print(f"[Royal Sigil Store] Failed to generate gear ID for {item_name}")
    
    else:
        print(f"[Royal Sigil Store] Warning: Unknown item type '{item_type}' for item_id={item_id}")

    if save_needed:
        save_characters(session.user_id, session.char_list)
