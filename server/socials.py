import secrets
import struct

from BitBuffer import BitBuffer
from Character import load_characters
from bitreader import BitReader
from constants import Entity
from globals import level_players, get_active_character_name, current_characters, build_room_thought_packet, \
    _send_error, send_chat_status, build_empty_group_packet, build_group_chat_packet, build_groupmate_map_packet


# Helpers
############################################################

def find_online_session(all_sessions, name):
    """Return session if player is online."""
    name = name.lower()
    for s in all_sessions:
        if getattr(s, "current_character", "").lower() == name:
            return s
    return None

def find_char_data_from_server_memory(name):
    """Returns the character save dict (already loaded on boot)."""
    for uid, current_char_name in current_characters.items():
        if current_char_name.lower() == name.lower():

            chars = load_characters(uid)
            for c in chars:
                if c["name"].lower() == name.lower():
                    return c
    return {}  # offline or unknown → dummy fallback

def get_live_friend_info(name, session, char):
    """Build the dynamic friend block (class, level, online)."""
    is_online = session is not None

    if is_online:
        class_name = session.current_char_dict.get("class", "Paladin")
        level = session.current_char_dict.get("level", 1)
    else:
        class_name = char.get("class", "Paladin")
        level = char.get("level", 1)

    return {
        "name": name,
        "className": class_name,
        "level": level,
        "isOnline": is_online,
    }

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

############################################################

def handle_zone_panel_request(session):
    level = session.current_level
    players = level_players.get(level)
    send_zone_players_update(session, players)

def handle_public_chat(session, data, all_sessions):
    br = BitReader(data[4:])
    entity_id = br.read_method_9()
    message   = br.read_method_13()

    # Forward raw unmodified packet to other players in the same level
    for other in all_sessions:
        if other is session:
            continue
        if not other.player_spawned:
            continue
        if other.current_level != session.current_level:
            continue

        other.conn.sendall(data)
        print(f"[{get_active_character_name(session)}] Says : \"{message}\"")

def handle_private_message(session, data, all_sessions):
    br = BitReader(data[4:])
    recipient_name = br.read_method_13()
    message        = br.read_method_13()

    # --- Find recipient session ---
    recipient_session = next(
        (s for s in all_sessions
         if s.authenticated
         and s.current_character
         and s.current_character.lower() == recipient_name.lower()),
        None
    )

    def make_packet(pkt_id, name, msg):
        bb = BitBuffer()
        bb.write_method_13(name)
        bb.write_method_13(msg)
        body = bb.to_bytes()
        return struct.pack(">HH", pkt_id, len(body)) + body

    sender_name = session.current_character

    if recipient_session:
        # 0x47 → delivered to recipient
        recipient_session.conn.sendall(make_packet(0x47, sender_name, message))

        # 0x48 → feedback to sender
        session.conn.sendall(make_packet(0x48, recipient_name, message))

        print(f"[PM] {sender_name} → {recipient_session.current_character}: \"{message}\"")
        return

    # --- Recipient not found → send error (0x44) ---
    err_txt = f"Player {recipient_name} not found"
    err_bytes = err_txt.encode("utf-8")
    pkt = struct.pack(">HH", 0x44, len(err_bytes) + 2) + struct.pack(">H", len(err_bytes)) + err_bytes
    session.conn.sendall(pkt)

    print(f"[PM-ERR] {sender_name} → {recipient_name} (NOT FOUND)")

def handle_room_thought(session, data, all_sessions):
    br = BitReader(data[4:])

    entity_id = br.read_method_4()
    text = br.read_method_13()

    level = session.current_level

    pkt = build_room_thought_packet(entity_id, text)

    for s in all_sessions:
        if s.player_spawned and s.current_level == level:
            try:
                s.conn.sendall(pkt)
            except:
                pass

def handle_start_skit(session, data, all_sessions):
    br = BitReader(data[4:])

    entity_id = br.read_method_9()
    is_chat_message = bool(br.read_method_15()) # if "True" message will also show in the players chat
    text = br.read_method_26()

    pkt = build_room_thought_packet(entity_id, text)

    for other in all_sessions:
        if other.player_spawned and other.current_level == session.current_level:
            try:
                other.conn.sendall(pkt)
            except:
                pass

    print(f"[SKIT] Entity {entity_id} says: '{text}'")


def handle_emote_begin(session, data, all_sessions):
    br = BitReader(data[4:])

    entity_id = br.read_method_4()
    emote = br.read_method_13()

    for other in all_sessions:
        if (other is not session
            and other.player_spawned
            and other.current_level == session.current_level):
            other.conn.sendall(data)


def handle_group_invite(session, data, all_sessions):
    br = BitReader(data[4:])
    invitee_name = br.read_method_13()

    invitee = next((
        s for s in all_sessions
        if s.authenticated
        and s.current_character
        and s.current_character.lower() == invitee_name.lower()
    ), None)

    if not invitee:
        _send_error(session.conn, f"Player {invitee_name} not found")
        return

    # Prevent inviting yourself
    if invitee is session:
        _send_error(session.conn, "You cannot invite yourself.")
        return

    # Reject if invitee is in another party
    if getattr(invitee, "group_id", None):
        _send_error(session.conn, f"{invitee_name} is already in a party")
        return

    # Build invite popup packet
    bb = BitBuffer()
    inviter_id   = session.clientEntID or 0
    inviter_name = session.current_character
    invite_text  = f"{inviter_name} has invited you to join a party"

    bb.write_method_9(inviter_id)
    bb.write_method_26(inviter_name)
    bb.write_method_26(invite_text)

    body = bb.to_bytes()
    invite_packet = struct.pack(">HH", 0x58, len(body)) + body

    invitee.conn.sendall(invite_packet)



def build_group_update_packet(members):
    """
    members = list of (session, is_leader)
    """
    bb = BitBuffer()

    # group exists
    bb.write_method_15(True)

    # group locked? (no)
    bb.write_method_15(False)

    # member count
    bb.write_method_4(len(members))

    for (sess, is_leader) in members:
        name = sess.current_character or ""

        bb.write_method_15(is_leader)

        # for now always True, we can make this dynamic later
        is_online = True
        bb.write_method_15(is_online)

        bb.write_method_26(name)

        # only if online:
        if is_online:
            ent = sess.entities.get(sess.clientEntID, {})
            x = int(ent.get("pos_x", 0))
            y = int(ent.get("pos_y", 0))

            bb.write_method_91(x)
            bb.write_method_91(y)

            # sameLevel flag
            same_level = True
            bb.write_method_15(same_level)
            #TODO...
            # if not same_level:
            #     level_name = getattr(sess, "current_level", "") or ""
            #     bb.write_method_26(level_name)

    payload = bb.to_bytes()
    return struct.pack(">HH", 0x75, len(payload)) + payload


def handle_query_message_answer(session, data, all_sessions):
    br = BitReader(data[4:])
    token    = br.read_method_9()
    name     = br.read_method_26()
    accepted = br.read_method_15()

    # Find inviter by entity ID
    inviter = next((s for s in all_sessions if s.clientEntID == token), None)
    if not inviter:
        return

    # DECLINED
    if not accepted:
        send_chat_status(inviter, f"{session.current_character} declined your invite.")
        return

    if getattr(session, "group_id", None):
        send_chat_status(inviter, f"{session.current_character} is already in a party.")
        return

    # Determine party for inviter
    if getattr(inviter, "group_id", None):
        gid = inviter.group_id
        group = inviter.group_members
    else:
        gid = secrets.randbits(16)
        inviter.group_id = gid
        inviter.group_members = [inviter]
        group = inviter.group_members

    # invitee to the same party
    session.group_id = gid
    group.append(session)
    session.group_members = group  # shared list

    # Build full party list for packet
    members = []
    for s in group:
        is_leader = (s is group[0])  # leader = first member
        members.append((s, is_leader))

    packet = build_group_update_packet(members)
    for s, _ in members:
        try:
            s.conn.sendall(packet)
        except:
            pass


# client only sends this when the player is in a party
def handle_map_location_update(session, data, all_sessions):
    br = BitReader(data[4:])

    map_x = br.read_method_236()
    map_y = br.read_method_236()

    session.map_x = map_x
    session.map_y = map_y

    # Broadcast to GROUP only
    for member in session.group_members:
        if member is session:
            continue  # skip sender

        pkt = build_groupmate_map_packet(session, map_x, map_y)
        try:
            member.conn.sendall(pkt)
        except:
            pass

def handle_group_kick(session, data, all_sessions):
    br = BitReader(data[4:])
    target_name = br.read_method_26()

    if not getattr(session, "group_id", None) or not session.group_members:
        send_chat_status(session, "You are not in a party.")
        return

    group = session.group_members
    leader = group[0]

    if session is not leader:
        send_chat_status(session, "Only the party leader can kick members.")
        return

    target = next((s for s in group if s.current_character.lower() == target_name.lower()), None)
    if not target:
        send_chat_status(session, f"{target_name} is not in your party.")
        return

    if target is session:
        send_chat_status(session, "You cannot kick yourself.")
        return

    group.remove(target)
    target.group_id = None
    target.group_members = []

    send_chat_status(target, "You have been removed from the party.")
    send_chat_status(session, f"You removed {target_name} from the party.")

    if len(group) == 1:
        lone = group[0]
        lone.group_id = None
        lone.group_members = []
        try:
            lone.conn.sendall(build_empty_group_packet())
        except:
            pass
        try:
            target.conn.sendall(build_empty_group_packet())
        except:
            pass
        return

    members = []
    for s in group:
        is_leader = (s is group[0])
        members.append((s, is_leader))
        s.group_members = group
        s.group_id = session.group_id

    pkt = build_group_update_packet(members)
    for s, _ in members:
        try:
            s.conn.sendall(pkt)
        except:
            pass

    try:
        target.conn.sendall(build_empty_group_packet())
    except:
        pass

def handle_group_leave(session, data, all_sessions):
    if not getattr(session, "group_id", None) or not session.group_members:
        send_chat_status(session, "You are not in a party.")
        return

    group = session.group_members
    if session not in group:
        session.group_id = None
        session.group_members = []
        send_chat_status(session, "You are not in a party.")
        return

    # Remove leaving player
    group.remove(session)
    old_gid = session.group_id
    session.group_id = None
    session.group_members = []

    send_chat_status(session, "You left the party.")

    try:
        session.conn.sendall(build_empty_group_packet())
    except:
        pass

    # ---------- PARTY DISBAND CONDITION ----------
    if len(group) <= 1:
        # Disband for the remaining member (if exists)
        if group:
            last = group[0]
            last.group_id = None
            last.group_members = []
            try:
                last.conn.sendall(build_empty_group_packet())
            except:
                pass
        return
    # --------------------------------------------

    # Party still has 2+ members -> new leader is first
    new_leader = group[0]

    for m in group:
        send_chat_status(m, f"{session.current_character} has left the party.")

    # Rebuild packet for remaining members
    members = []
    for s in group:
        is_leader = (s is new_leader)
        members.append((s, is_leader))
        s.group_members = group
        s.group_id = old_gid

    pkt = build_group_update_packet(members)
    for s, _ in members:
        try:
            s.conn.sendall(pkt)
        except:
            pass


def handle_group_leader(session, data, all_sessions):
    br = BitReader(data[4:])
    target_name = br.read_method_26()

    # Must be in a party
    if not getattr(session, "group_id", None) or not session.group_members:
        send_chat_status(session, "You are not in a party.")
        return

    group = session.group_members
    leader = group[0]

    # Only leader may promote
    if session is not leader:
        send_chat_status(session, "Only the party leader can assign leadership.")
        return

    # Find target inside the party
    target = next((s for s in group if s.current_character.lower() == target_name.lower()), None)
    if not target:
        send_chat_status(session, f"{target_name} is not in your party.")
        return

    if target is session:
        send_chat_status(session, "You are already the leader.")
        return

    # Promote target
    group.remove(target)
    group.insert(0, target)

    # Notify members
    send_chat_status(session, f"You made {target_name} the party leader.")
    send_chat_status(target, "You are now the party leader.")

    for m in group:
        if m not in (session, target):
            send_chat_status(m, f"{target_name} is now the party leader.")

    # Rebuild the group packet
    members = []
    for s in group:
        is_leader = (s is group[0])
        members.append((s, is_leader))
        s.group_members = group
        s.group_id = session.group_id

    pkt = build_group_update_packet(members)

    # Send to all
    for s, _ in members:
        try:
            s.conn.sendall(pkt)
        except:
            pass

def handle_send_group_chat(session, data, all_sessions):
    br = BitReader(data[4:])
    message = br.read_method_26()

    if not message.strip():
        return

    # Must be in a party
    if not getattr(session, "group_id", None) or not session.group_members:
        send_chat_status(session, "You are not in a party.")
        return

    group = session.group_members
    sender_name = session.current_character

    pkt = build_group_chat_packet(sender_name, message)
    print(f" [Group chat] {sender_name} Says : {message}")

    # Send to ALL members including sender
    for m in group:
        try:
            m.conn.sendall(pkt)
        except:
            pass