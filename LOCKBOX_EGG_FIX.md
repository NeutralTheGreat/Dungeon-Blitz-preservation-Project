## Lockbox Egg Reward Fix - Change Summary

### Problem
Random level 10 pet rewards from lockboxes were not working. Rewards were being added to the hatchery (OwnedEggsID) as eggs instead of being added directly to the player inventory as level 10 pets.

### Solution Implemented

**File: `server/Commands.py`** (handle_lockbox_reward function)

#### Change 1: Updated reward selection logic (Line ~540)
**Before:**
```python
elif reward_type == "egg":
    # Egg (client displays as "Pet (Level 10)") - only if hatchery has room (max 8 slots)
    MAX_EGG_SLOTS = 8
    owned_eggs = char.get("OwnedEggsID", [])
    if len(owned_eggs) < MAX_EGG_SLOTS:
        available_rewards[idx] = reward_data
```

**After:**
```python
elif reward_type == "egg":
    # Egg reward - adds Level 10 pet directly to inventory
    # No capacity limit for pet inventory (pets are unlimited)
    available_rewards[idx] = reward_data
```

**Reason:** Removed hatchery capacity check since eggs are now added directly as pets to the unlimited pet inventory.

#### Change 2: Updated egg reward grant logic (Line ~758)
**Before:**
```python
elif reward_type == "egg":
    # Egg reward - client displays as "Pet (Level 10)". Add egg to OwnedEggsID (hatchery).
    egg_id = get_egg_id(name)
    if egg_id and egg_id > 0:
        owned_eggs = char.get("OwnedEggsID", [])
        if len(owned_eggs) < 8:
            owned_eggs.append(egg_id)
            char["OwnedEggsID"] = owned_eggs
            save_needed = True
            print(f"[Lockbox] {char['name']} received egg {name} (ID: {egg_id})")
        else:
            print(f"[Lockbox] {char['name']} hatchery full, skipping egg grant")
    else:
        print(f"[Lockbox] Warning: Unknown egg '{name}'")
```

**After:**
```python
elif reward_type == "egg":
    # Egg reward - Add as Level 10 pet directly to inventory
    # (EggID matches PetID in data, so egg_id is the pet type ID)
    egg_id = get_egg_id(name)
    if egg_id and egg_id > 0:
        pet_def = next((p for p in PET_TYPES if p.get("PetID") == egg_id), None)
        if pet_def:
            pet_type_id = pet_def["PetID"]
            starting_level = 10  # Level 10 from egg reward
            
            pets = char.get("pets", [])
            special_id = max((p.get("special_id", 0) for p in pets), default=0) + 1
            
            new_pet = {
                "typeID": pet_type_id,
                "special_id": special_id,
                "level": starting_level,
                "xp": 0,
            }
            
            pets.append(new_pet)
            char["pets"] = pets
            
            # Send pet notification
            send_new_pet_packet(session, pet_type_id, special_id, starting_level, suppress=False)
            save_needed = True
            print(f"[Lockbox] {char['name']} received level {starting_level} pet {pet_def.get('DisplayName', name)}")
        else:
            print(f"[Lockbox] Warning: Pet definition not found for egg ID {egg_id}")
    else:
        print(f"[Lockbox] Warning: Unknown egg '{name}'")
```

**Key Changes:**
1. Now adds the pet directly to the `pets` inventory instead of `OwnedEggsID` (hatchery)
2. Pet is created with `level: 10` (starts at level 10)
3. Pet receives a unique `special_id` for tracking
4. Client notification is sent using `send_new_pet_packet()` with the level 10 info
5. Starts with 0 XP

### How It Works
1. **EggID = PetID**: The egg_types.json and pet_types.json share the same IDs
   - EggID 1 (GenericBrown) → PetID 1 (Great Horned Owl)
   - EggID 2 (CommonBrown) → PetID 2 (Questing Cherub)
   - etc.
2. When a player gets an egg reward from a lockbox, it's now converted to a level 10 pet
3. The pet is immediately available in the player's pet inventory at level 10

### Lockbox Egg Rewards
The reward_map includes 4 egg reward options (indices 2-5):
- **Index 2**: "GenericBrown" → Level 15 OwlRed → **Level 10 in inventory**
- **Index 3**: "CommonBrown" → Level 30 AngelRed → **Level 10 in inventory**
- **Index 4**: "OrdinaryBrown" → Level 25 FalconRed → **Level 10 in inventory**
- **Index 5**: "PlainBrown" → Level 30 CrowRed → **Level 10 in inventory**

### Testing
- ✅ All 36 egg types successfully map to their corresponding pets
- ✅ Python syntax validated
- ✅ Logic flow verified with test script

### Impact
- Players now receive random level 10 pets from lockbox rewards
- No more hatchery capacity issues (pets are unlimited)
- Better reward progression vs eggs (immediate level 10 instead of level 1 after hatching)
