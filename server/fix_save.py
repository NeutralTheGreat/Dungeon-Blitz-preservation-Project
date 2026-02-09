import json
import os
import glob

def update_lockbox_file(filepath):
    """Update lockbox keys and count in a single save file to 25."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False
    
    # Update all characters
    for idx, char in enumerate(data.get('characters', [])):
        # Set DragonKeys (lockbox keys) to 25
        old_keys = char.get('DragonKeys', 0)
        char['DragonKeys'] = 25
        print(f"  [{os.path.basename(filepath)}] Char {idx}: DragonKeys {old_keys} -> 25")

        # Set lockbox count to 25 for lockboxID 1
        if 'lockboxes' in char:
            updated_existing = False
            for box in char['lockboxes']:
                if box.get('lockboxID') == 1:
                    old_count = box.get('count', 0)
                    box['count'] = 25
                    print(f"  [{os.path.basename(filepath)}] Char {idx}: Lockbox count {old_count} -> 25")
                    updated_existing = True
                    break
            if not updated_existing:
                char['lockboxes'].append({'lockboxID': 1, 'count': 25})
                print(f"  [{os.path.basename(filepath)}] Char {idx}: Added lockboxID 1 with count 25")
        else:
            char['lockboxes'] = [{'lockboxID': 1, 'count': 25}]
            print(f"  [{os.path.basename(filepath)}] Char {idx}: Created new lockboxes entry with count 25")

    # Write results
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"✓ {os.path.basename(filepath)} updated successfully!")
        return True
    except Exception as e:
        print(f"Error writing {filepath}: {e}")
        return False

# Find all save files (*.json) in saves directory
saves_dir = 'saves'
json_files = glob.glob(os.path.join(saves_dir, '*.json'))

if not json_files:
    print("No JSON files found in saves directory")
else:
    print(f"Found {len(json_files)} JSON file(s)")
    for filepath in json_files:
        print(f"\nProcessing: {filepath}")
        update_lockbox_file(filepath)

print('\n=== All save files updated successfully! ===')
