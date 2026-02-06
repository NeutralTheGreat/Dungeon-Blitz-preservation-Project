import sys
import os
import json
import random

# Add server directory to path
sys.path.append("server")

import game_data

def verify_specific_drops():
    print("Loading data...")
    game_data.load_ent_types()
    game_data.load_gear_data()
    
    print(f"Loaded {len(game_data._gear_data.get('realm_drops', {}))} realms and {len(game_data._gear_data.get('boss_drops', {}))} bosses.")

    # Test Cases
    test_cases = [
        ("GoblinClub", "Goblin"), 
        ("GrayGhostLord", "Ghost"), # Boss should use Boss drops first, but fits Realm
        ("DeepLizardWarrior", "Lizard"),
        ("CougarWarriorHard", "Lion") # From my earlier view
    ]
    
    for ent_name, expected_realm in test_cases:
        print(f"\nTesting {ent_name} (Expected Realm: {expected_realm} context)...")
        
        # Run multiple times to see variety
        ids = set()
        for _ in range(20):
            gid = game_data.get_gear_id_for_entity(ent_name)
            if gid:
                ids.add(gid)
        
        if not ids:
            print(f"FAILED: No drops found for {ent_name}")
            continue
            
        print(f"Found Gear IDs: {sorted(list(ids))}")
        
        # Verify IDs belong to the expected realm/boss
        # Load the raw data to check
        valid_ids = []
        if ent_name in game_data._gear_data["boss_drops"]:
            valid_ids = game_data._gear_data["boss_drops"][ent_name]
            print("  (Using Boss Table)")
        elif expected_realm in game_data._gear_data["realm_drops"]:
            valid_ids = game_data._gear_data["realm_drops"][expected_realm]
            print("  (Using Realm Table)")
        
        all_valid = True
        for gid in ids:
            if gid not in valid_ids:
                print(f"  [ERROR] ID {gid} is NOT in valid list for {ent_name}!")
                all_valid = False
        
        if all_valid:
            print("  [PASS] All generated IDs are valid.")

    # Test an invalid entity
    print("\nTesting Invalid Entity...")
    gid = game_data.get_gear_id_for_entity("NonExistentMob")
    if gid is None:
        print("  [PASS] Correctly returned None.")
    else:
        print(f"  [FAIL] Returned {gid} for non-existent mob.")

if __name__ == "__main__":
    verify_specific_drops()
