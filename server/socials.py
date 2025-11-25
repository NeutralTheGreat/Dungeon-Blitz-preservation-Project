import struct

from BitBuffer import BitBuffer
from constants import Entity
from globals import level_players

def build_and_send_zone_player_list(session, valid_entries):
    bb = BitBuffer()
    for e in valid_entries:
        bb.write_method_15(True)
        bb.write_method_13(e["name"])
        bb.write_method_6(e["classID"], Entity.const_244)
        bb.write_method_6(e["level"], Entity.MAX_CHAR_LEVEL_BITS)

    # terminator
    bb.write_method_15(False)

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x96, len(payload)) + payload
    session.conn.sendall(pkt)

    print(f"[{session.addr}] ZonePlayerList ({len(valid_entries)} players)")

def send_zone_players_update(session, players):
    valid_entries = []
    for entry in players:
        other_sess = entry.get("session")

        char = getattr(other_sess, "current_char_dict", None)

        class_name = char["class"]

        classID = {"Paladin": 0, "Rogue": 1, "Mage": 2}[class_name]

        level = char["level"]

        valid_entries.append({
            "name": char["name"],
            "classID": classID,
            "level": level,
        })
    build_and_send_zone_player_list(session, valid_entries)

def handle_zone_panel_request(session):
    level = session.current_level
    players = level_players.get(level)
    send_zone_players_update(session, players)

