import os
import json

PACKET_HEADER_SIZE = 4
NUM_TALENT_SLOTS = 27
CONST_529 = [5,2,3,5,5,3,2,3,2,5,2,3,5,5,3,2,3,2,5,2,3,5,5,3,2,3,2]
CLASS_118_CONST_127 = 6
const_228 = 4
GAME_CONST_209 = 4
ENTITY_CONST_244    = 2
class_9_const_28 = 5
class_1_const_254 = 7
class_64_const_499 = 2
class_64_const_218 = 5
class_111_const_432 = 9
class_10_const_665 = 4
GS_BITS = 2
MAX_CHAR_LEVEL_BITS = 6
class_10_const_83  = 7
class_16_const_167 = 6
class_7_const_19 = 7
class_9_const_129 = 5
GEARTYPE_BITS = 11
SLOT_BIT_WIDTHS = []

FRAMEBITS_TO_CLASSKEY = {
        533: "executioner",
        545: "shadowwalker",
        437: "soulthief",
        442: "sentinel",
        415: "justicar",
        472: "templar",
        479: "frostwarden",
        491: "flameseer",
        550: "necromancer",
    }

def index_to_node_id(index: int) -> int:
    """
    Reverse mapping of client method_191:
    Array index (0-26) -> NodeID (1-27)
    """
    if index < 9:  # indices 0-8 → NodeID 1-9
        return index + 1
    elif index < 18:  # indices 9-17 → NodeID 11-19
        return index + 2
    else:  # indices 18-26 → NodeID 20-27
        return index + 3

def method_233(frame_bits: int) -> str:
    return FRAMEBITS_TO_CLASSKEY.get(frame_bits, "")

def client_index_to_node_id(i: int) -> int:
    """Emulates  method_191"""
    if i < 9:
        return i + 1
    elif i < 18:
        return i + 2
    else:
        return i + 3

MASTERCLASS_TO_BUILDING = {
    # Rogue
    1: 9,   # ExecutionerTower
    2: 10,  # ShadowwalkerTower
    3: 11,  # SoulthiefTower

    # Paladin
    4: 3,   # JusticarTower
    5: 4,   # SentinelTower
    6: 5,   # TemplarTower

    # Mage
    7: 6,   # FrostwardenTower
    8: 7,   # FlameseerTower
    9: 8    # NecromancerTower
}

for x in CONST_529:
    w = 0
    if x <= 2:
        w = 1
    if x <= 4:
        w = 2
    if x <= 5:
        w = 3
    SLOT_BIT_WIDTHS.append(w)

def method_277(idx: int) -> int:
    x = CONST_529[idx]
    w = 0
    if x <= 2: w = 1
    if x <= 4: w = 2
    if x <= 5: w = 3
    return w

class Bossfight:
    const_1145 = 0
    const_821 = 1
    const_756 = 2
    const_810 = 3

class Mission:
    const_213 = 0 # Not started
    const_58  = 1 # In progress
    const_72  = 2 # Completed

class class_119:
    const_1398 = 10
    const_1416 = 15
    const_1331 = 115
    const_1237 = 8
    const_659 = 7
    const_896 = 6
    const_1283 = 5
    const_597 = 4
    const_1199 = 3
    const_1150 = 2
    const_1225 = 1
    const_771 = 0
    const_723 = 10
    const_228 = 4
    const_679 = 600
    const_490 = 810
    const_1418 = 560

ENTITYSTATE_DEAD   = 2    # 3
ENTITYSTATE_ALIVE  = 1  # 1

CLASS_NAME_TO_ID = {
    "Paladin": 0,
    "Rogue":   1,
    "Mage":    2,
}

class class_9:
    const_851 = 2
    const_129 = 5
    const_28 = 5
    const_1334 = 2
    const_214 = 10
    const_1404 = 0
    const_1390 = 1

class door:
    DOORSTATE_CLOSED = 0
    DOORSTATE_STATIC = 1
    DOORSTATE_MISSION = 2
    DOORSTATE_MISSIONREPEAT = 3
    DOORSTATE_LOCKED = 4

class class_10:
    const_83 = 7
    const_665 = 4
    const_105 = 10

class class_8:
    const_658 = 7
    const_731 = 7

class class_7 :
    const_19 = 7
    const_75 = 6

class class_20 :
    const_297 = 7

class class_3 :
    const_69 = 5
    var_1415 = 1  # ForgeXP
    var_2082 = 2  # RareBoost
    var_1374 = 3  # LegendaryBoost
    var_1462 = 4  # ArtisanBoost

class Entity:
    TEAM_BITS = 2
    const_316 = 2  # Entity state bit count
    const_399 = 1  # Sleep state
    const_467 = 2  # Drama state The entity become untarketable
    const_6 = 3 # Entity Dead State
    const_78 = 0
    const_244 = 2
    const_172 = 3
    MAX_CHAR_LEVEL_BITS = 6
    Dye_Gold_Cost = [0, 455, 550, 595, 650, 735, 795, 890, 965, 1075, 1155, 1285, 1385, 1520, 1685, 1810, 1985, 2180,
                        2380, 2600, 2845, 3090, 3375, 3710, 4025, 4410, 4790, 5225, 5705, 6215, 6750, 7340, 8020, 8690,
                        9455, 10300, 11230, 12185, 13255, 14405, 15635, 17010, 18475, 20050, 21725, 23650, 25640, 27835,
                        30165, 32730, 35540]
    Dye_Idols_Cost = [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4,
                         4, 5, 5, 5, 6, 6, 7, 7, 8, 8, 9, 10, 11, 11, 12, 13, 14, 16, 17]

class PowerType :
    const_423 = 7

class LinkUpdater:
    MIN_TIME_BETWEEN_UPDATES = 125
    MIN_TIME_BETWEEN_POS_UPDATES = 1000
    VELOCITY_DEFLATE = 10000
    VELOCITY_INFLATE = 10000

class Game :
    const_209 = 4
    const_526 = 0
    const_181 = 180
    const_703 = 1200
    const_390 = 5
    const_646 = 4

class class_118 :
    NUM_TALENT_SLOTS = 27
    const_43 = 27
    const_529 = [5, 2, 3, 5, 5, 3, 2, 3, 2, 5, 2, 3, 5, 5, 3, 2, 3, 2, 5, 2, 3, 5, 5, 3, 2, 3, 2]
    const_1304 = 90
    const_1246 = 65
    const_195 = 5
    const_127 = 6
    ABILITY6_POINTS_PREREQ = 40
    ABILITY6_NODE_PREREQ  = 18
    ABILITY5_POINTS_PREREQ = 20
    ABILITY5_NODE_PREREQ = 8

class class_111 :
    const_509 = 0
    const_286 = 1
    const_264 = 2
    const_1101 = 511
    const_432 = 9

class class_21:
    const_1338 = 20
    const_1365 = 165
    const_640 = 185
    const_763 = 250
    const_50 = 8

class LockboxType:
    ID_BITS = 8

class EntType:
    MAX_SLOTS = 7
    STATE_IDLE = 6
    STATE_ACTIVE = 78
    CHAR_COLOR_BITSTOSEND = 24

class DyeType:
    BITS = 8

class class_1:
    const_254 = 7
    const_765 = 2
    const_405 = 91
    const_1193 = 92
    DOUBLEFIND1_CHARMID = 93
    DOUBLEFIND2_CHARMID = 94
    DOUBLEFIND3_CHARMID = 95
    const_459 = 96

class class_64:
    const_101 = 16

class GearType:
    GEARTYPE_BITSTOSEND = 11
    const_348          = 3
    const_176          = 2

class class_13:
      const_949 = 3

class class_66:
    const_465 = 3
    const_409 = 6
    const_571 = 2
    const_1412 = 1
    const_1410 = 2
    const_1420 = 3
    const_185 = 0
    const_200 = 1
    const_534 = 2
    const_495 = 50
    const_948 = 5
    RESEARCH_DURATIONS = [0, 180, 7200, 14400, 21600, 37800, 54000, 70200, 86400, 108000, 129600, 150750,
                          171900, 195750, 219600, 268500, 317400, 337500, 357600, 434850, 512100, 532575, 553050,
                          575175, 597300, 621200, 645100, 670900, 696700, 724575, 752450, 782550, 812650, 845150,
                          877650, 912750, 947850, 985775, 1023700, 1064650, 1105600, 1149825, 1194050, 1241800, 1289550,
                          1341125, 1392700, 1448400, 1504100, 1564275, 1624450]
    RESEARCH_COSTS = [0, 0, 2805, 6300, 11187, 18009, 27133, 39230, 55492, 76352, 103326, 138087, 182677, 238420,
                      309610, 398435, 508501, 646504, 817051, 1028027, 1287751, 1608088, 2000327, 2479956, 3067822,
                      3781585, 4084112, 4410841, 4763708, 5144805, 5556389, 6000900, 6480972, 6999450, 7559406, 8164158,
                      8817291, 9522674, 10284488, 11107247, 11995827, 12955493, 13991932, 15111287, 16320190, 17625805,
                      19035869, 20558739, 22203438, 23979713, 25898090]
    IDOL_COST = [0, 0, 2, 4, 6, 10, 14, 20, 28, 37, 41, 45, 51, 59, 68, 80, 95, 113, 122, 132, 145, 161, 181, 193, 204,
                  219, 225, 231, 238, 246, 254, 263, 273, 283, 291, 299, 308, 318, 329, 340, 352, 366, 380, 396, 412,
                  431, 450, 471, 494, 519, 545]


BUILDING_ID_TO_STATS_INDEX = {
    2: 0,    # Magic Forge
    12: 1,   # Keep
    3: 2, 4: 3, 5: 4,  # Paladin Talents
    6: 2, 7: 3, 8: 4,  # Mage Talents
    9: 2, 10: 3, 11: 4,  # Rogue Talents
    1: 5,    # Tome
    13: 6,   # Hatcher
}

NEWS_EVENTS = {
    1: ["a_NewsGoldIcon",      "Double Gold Event",     "Double Gold Event",       "http://www.dungeonblitz.com/",1786841238],
    2: ["a_NewsGearIcon",      "Double Gear Event",     "Double Gear Event",       "http://www.dungeonblitz.com/",1786841238],
    3: ["a_NewsMatsIcon",      "Double Material Event", "Double Material Event",   "http://www.dungeonblitz.com/",1786841238],
    4: ["a_NewsXPIcon",        "Double XP Event",       "Double XP Event",         "http://www.dungeonblitz.com/",1786841238],
    5: ["a_NewsPetXPIcon",     "Double Pet XP Event",   "Double Pet XP Event",     "http://www.dungeonblitz.com/",1786841238],
}
               #Loaders
################################################################
with open("data/DyeTypes.json", "r", encoding="utf-8") as f:
    DYE_DATA = json.load(f)

def get_dye_color(dye_id):
    dye = DYE_DATA.get(str(dye_id))
    if dye:
        return dye["color"]
    return None

def load_ability_data():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "data/AbilityTypes.json")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except FileNotFoundError:
        print(f"Error: AbilityTypes.json not found at {json_path}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse AbilityTypes.json: {e}")
        return []
ABILITY_DATA = load_ability_data()

def get_ability_info(ability_id, rank):
    for entry in ABILITY_DATA:
        if entry.get("AbilityID") == str(ability_id) and entry.get("Rank") == str(rank):
            return {
                "AbilityID": int(entry.get("AbilityID", 0)),
                "Rank": int(entry.get("Rank", 0)),
                "GoldCost": int(entry.get("GoldCost", 0)),
                "IdolCost": int(entry.get("IdolCost", 0)),
                "UpgradeTime": int(entry.get("UpgradeTime", 0))
            }
    return None
BUILDING_DATA = []

def load_building_data():
    global BUILDING_DATA
    if not BUILDING_DATA:
        with open("data/BuildingTypes.json", "r", encoding="utf-8") as f:
            BUILDING_DATA = json.load(f)

def find_building_data(building_id: int, rank: int):
    for b in BUILDING_DATA:
        if int(b["BuildingID"]) == building_id and int(b["Rank"]) == rank:
            return b
    return None