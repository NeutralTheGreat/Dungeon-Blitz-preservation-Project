import struct

from BitBuffer import BitBuffer
from bitreader import BitReader
from globals import GS
from login import handle_gameserver_login
"""
Some context : 

if "<DEVFLAG_MASTER_CLIENT />" is enabled in the "devSettings" 
the client will send a "0x1E" packet instead of the normal "0x1f" packet
this code is just good enough to get the player loading in game nothing more 
i played around for a bit and activating this option dint seem to actually provide anything of value
this why i decided to stop here 

Note : attempting to change levels will break the game also attempting to use any of the buildings in "CraftTown" wont work
"""

def build_fake_login_packet(token):
    bb = BitBuffer()
    bb.write_method_9(token)
    bb.write_method_26("")
    bb.write_method_15(False)
    body = bb.to_bytes()
    return struct.pack(">HH", 0x1F, len(body)) + body

def DEVFLAG_MASTER_CLIENT(session, data):
    br = BitReader(data[4:])
    value = br.read_method_9()
    boolean = br.read_method_15()

    print(f" value : {value} : Boolean {boolean}")

    for t, (char, _, _) in GS.pending_world.items():
        if session.user_id is None or char.get("user_id") == session.user_id:
            handle_gameserver_login(session, build_fake_login_packet(t))
            return


def handle_quest_progress_update(session, data):
    br = BitReader(data[4:])
    progress = br.read_method_4()
    #print(f" Quest/Room progress = {progress}")
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)


def handle_level_state(session, data):
    br = BitReader(data[4:])
    state_a = br.read_method_26()
    state_b = br.read_method_26()
    #print(f" LevelState: '{state_a}', '{state_b}'")
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_play_sound(session, data):
    br = BitReader(data[4:])
    room_id = br.read_method_4()
    sound_name = br.read_method_26()
    volume_scaled = br.read_method_4()
    volume = volume_scaled / 100.0
    #print(f" PlaySound room={room_id} sound='{sound_name}' volume={volume}")
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_action_update(session, data):
    br = BitReader(data[4:])
    room_id = br.read_method_4()
    action_id = br.read_method_4()
    #print(f" ActionUpdate room={room_id} action={action_id}")
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_emote(session, data):
    br = BitReader(data[4:])
    room_id = br.read_method_4()
    actor_name = br.read_method_26()
    emote_name = br.read_method_26()
    loop_flag = br.read_method_15()
    #print(
    #    f"Emote room={room_id} actor='{actor_name}' "
    #    f"emote='{emote_name}' loop={loop_flag}"
    #)
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)


def handle_room_state_update(session, data):
    br = BitReader(data[4:])
    room_id = br.read_method_4()
    room_state = br.read_method_4()
    #print(f" RoomStateUpdate room={room_id} state={room_state}")
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_room_event_start(session, data):
    br = BitReader(data[4:])
    room_id = br.read_method_4()
    flag = br.read_method_15()
    #print(f" RoomEventStart room={room_id} flag={flag}")
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_room_info_update(session, data):
    br = BitReader(data[4:])
    room_id = br.read_method_4()
    info_a = br.read_method_4()
    info_b = br.read_method_26()
    info_c = br.read_method_4()
    info_d = br.read_method_26()
    #print(
    #    f"RoomInfoUpdate room={room_id} "
    #    f"a={info_a} b='{info_b}' c={info_c} d='{info_d}'"
    #)
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_set_untargetable(session, data):
    br = BitReader(data[4:])
    entity_id = br.read_method_4()
    untargetable = br.read_method_15()
    #print(
    #    f"SetUntargetable entity={entity_id} "
    #    f"untargetable={untargetable}"
    #)
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)

def handle_room_close(session, data):
    br = BitReader(data[4:])
    room_id = br.read_method_4()
    #print(f"RoomClose / Reset room={room_id}")
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)


def handle_room_unlock(session, data):
    br = BitReader(data[4:])
    room_id = br.read_method_4()
    #print(f"RoomUnlock room={room_id}")
    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)


def handle_room_boss_info(session, data):
    br = BitReader(data[4:])

    room_id    = br.read_method_4()
    boss1_id   = br.read_method_4()
    boss1_name = br.read_method_26()
    boss2_id   = br.read_method_4()
    boss2_name = br.read_method_26()

    #print(
    #    f"[0xAC] ROOM_BOSS_INFO room={room_id} "
    #    f"boss1=({boss1_id}, '{boss1_name}') "
    #    f"boss2=({boss2_id}, '{boss2_name}')"
    #)

    for other in GS.all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)
