import json

# Read the save file
with open(r'saves/2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Update the first character
char = data['characters'][0]

# Set DragonKeys (lockbox keys) to 5
old_keys = char.get('DragonKeys', 0)
char['DragonKeys'] = 5
print(f"DragonKeys: {old_keys} -> 5")

# Set lockbox count to 5
if 'lockboxes' in char:
    for box in char['lockboxes']:
        if box.get('lockboxID') == 1:
            print(f"Old lockbox count: {box.get('count', 0)}")
            box['count'] = 5
            print(f"New lockbox count: 5")
else:
    char['lockboxes'] = [{'lockboxID': 1, 'count': 5}]
    print('Created new lockboxes entry with count 5')

# Write results
with open(r'saves/2.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print('Save file updated successfully!')
