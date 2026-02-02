import sys
import os
# sys.path.append('.') # implicitly in path
try:
    import game_data
    print("Import successful")
    game_data.load_class_gear_ids()
    print("Maps loaded")
    print("Paladin gear example:", game_data.get_random_gear_id("Paladin"))
    print("Rogue gear example:", game_data.get_random_gear_id("Rogue"))
    print("Fallback gear example:", game_data.get_random_gear_id("InvalidClass"))
except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()
