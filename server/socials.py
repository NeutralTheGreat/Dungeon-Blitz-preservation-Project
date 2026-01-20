import secrets
import struct

from BitBuffer import BitBuffer
from accounts import load_characters, save_characters, find_user_by_character_name
from GameState import state
from bitreader import BitReader
from constants import Entity
from globals import get_active_character_name, build_room_thought_packet, send_chat_status, build_empty_group_packet, build_group_chat_packet, build_groupmate_map_packet, GS


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
    for uid, current_char_name in GS.current_characters.items():
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

# Group helpers
############################################################

def char_key(session):
    return getattr(session, "current_character", "") or ""

def get_group_for_session(session):
    name = getattr(session, "current_character", None)
    if not name:
        return None, None
    return state.get_group_for_name(name)

def online_group_members(group, all_sessions):
    if not group:
        return []

    members = []
    for name_key in group["members"]:
        # stored as lowercase, but find_online_session already lowercases
        sess = find_online_session(all_sessions, name_key)
        if not sess:
            continue
        is_leader = (name_key == group["leader"])
        members.append((sess, is_leader))
    return members

def update_session_group_cache(gid, members):
    sessions = [s for (s, _) in members]
    for s in sessions:
        s.group_id = gid
        s.group_members = sessions

############################################################

def handle_zone_panel_request(session, data):
    level = session.current_level
    players = GS.level_players.get(level)
    send_zone_players_update(session, players)

def handle_public_chat(session, data):
    br = BitReader(data[4:])
    entity_id = br.read_method_9()
    message   = br.read_method_13()

    print(f"[{get_active_character_name(session)}] Says : \"{message}\"")

    # Forward raw unmodified packet to other players in the same level
    for other in GS.all_sessions:
        if other is session:
            continue
        if not other.player_spawned:
            continue
        if other.current_level != session.current_level:
            continue

        other.conn.sendall(data)


def handle_private_message(session, data):
    br = BitReader(data[4:])
    recipient_name = br.read_method_13()
    message        = br.read_method_13()

    # --- Find recipient session ---
    recipient_session = next(
        (s for s in GS.all_sessions
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

def handle_room_thought(session, data):
    br = BitReader(data[4:])

    entity_id = br.read_method_4()
    text = br.read_method_13()

    level = session.current_level

    pkt = build_room_thought_packet(entity_id, text)

    for s in GS.all_sessions:
        if s.player_spawned and s.current_level == level:
            try:
                s.conn.sendall(pkt)
            except:
                pass

def handle_start_skit(session, data):
    br = BitReader(data[4:])

    entity_id = br.read_method_9()
    is_chat_message = bool(br.read_method_15()) # if "True" message will also show in the players chat
    text = br.read_method_26()

    pkt = build_room_thought_packet(entity_id, text)

    for other in GS.all_sessions:
        if other.player_spawned and other.current_level == session.current_level:
            try:
                other.conn.sendall(pkt)
            except:
                pass

    #print(f"[SKIT] Entity {entity_id} says: '{text}'")


def handle_emote_begin(session, data):
    br = BitReader(data[4:])

    entity_id = br.read_method_4()
    emote = br.read_method_13()

    for other in GS.all_sessions:
        if (other is not session
            and other.player_spawned
            and other.current_level == session.current_level):
            other.conn.sendall(data)


def handle_group_invite(session, data):
    br = BitReader(data[4:])
    invitee_name = br.read_method_13()

    invitee = next((
        s for s in GS.all_sessions
        if s.authenticated
        and s.current_character
        and s.current_character.lower() == invitee_name.lower()
    ), None)

    if not invitee:
        send_chat_status(session, f"Player {invitee_name} not found")
        return

    # Prevent inviting yourself
    if invitee is session:
        send_chat_status(session, "You cannot invite yourself.")
        return

    # Reject if invitee is already in a party
    if state.get_gid_for_name(invitee.current_character):
        send_chat_status(session, f"{invitee_name} is already in a party")
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
    if not members:
        return build_empty_group_packet()

    leader_session = members[0][0]
    leader_level = getattr(leader_session, "current_level", None)

    bb = BitBuffer()

    bb.write_method_15(True)   # group exists
    bb.write_method_15(False)  # group locked always false

    # member count
    bb.write_method_4(len(members))

    for (sess, is_leader) in members:
        name = sess.current_character or ""

        bb.write_method_15(is_leader)

        is_online = (
            getattr(sess, "authenticated", False) and
            not getattr(sess, "disconnected", False)
        )
        bb.write_method_15(is_online)

        bb.write_method_26(name)

        # only if online:
        if is_online:
            ent = sess.entities.get(sess.clientEntID, {})
            x = int(ent.get("pos_x", 0))
            y = int(ent.get("pos_y", 0))

            bb.write_method_91(x)
            bb.write_method_91(y)

            # SAME LEVEL
            member_level = getattr(sess, "current_level", None)
            same_level = (member_level == leader_level)
            bb.write_method_15(same_level)

            if not same_level:
                # Client expects zone name so it can show it in party UI
                bb.write_method_26(member_level or "")
        else:
            # Offline: send placeholder coords + sameLevel=False
            bb.write_method_91(0)
            bb.write_method_91(0)
            bb.write_method_15(False)
            # And the client expects level name here too
            bb.write_method_26("Offline")

    payload = bb.to_bytes()
    return struct.pack(">HH", 0x75, len(payload)) + payload


def handle_query_message_answer(session, data):
    br = BitReader(data[4:])
    token    = br.read_method_9()
    name     = br.read_method_26()
    accepted = br.read_method_15()

    # Find inviter by entity ID
    inviter = next((s for s in GS.all_sessions if s.clientEntID == token), None)
    if not inviter:
        return

    if not accepted:
        send_chat_status(inviter, f"{session.current_character} declined your invite.")
        return

    if state.get_gid_for_name(session.current_character):
        send_chat_status(inviter, f"{session.current_character} is already in a party.")
        return

    inviter_name = inviter.current_character
    invitee_name = session.current_character

    # Determine or create party for inviter
    gid, group = state.get_group_for_name(inviter_name)
    if not group:
        gid = secrets.randbits(16)
        gid, group = state.create_group(inviter_name, gid)

    # Add invitee to same group
    state.add_member(gid, invitee_name)

    # Build full party list for packet
    members = online_group_members(group, GS.all_sessions)
    update_session_group_cache(gid, members)

    packet = build_group_update_packet(members)
    for s, _ in members:
        s.conn.sendall(packet)


# client only sends this when the player is in a party
def handle_map_location_update(session, data):
    br = BitReader(data[4:])

    map_x = br.read_method_236()
    map_y = br.read_method_236()

    session.map_x = map_x
    session.map_y = map_y

    gid, group = get_group_for_session(session)
    if not group:
        return

    # Broadcast to GROUP only
    for member, _ in online_group_members(group, GS.all_sessions):
        if member is session:
            continue  # skip sender

        pkt = build_groupmate_map_packet(session, map_x, map_y)
        member.conn.sendall(pkt)


def handle_group_kick(session, data):
    br = BitReader(data[4:])
    target_name = br.read_method_26()
    target_key = target_name.strip().lower()

    gid, group = get_group_for_session(session)
    if not group:
        send_chat_status(session, "You are not in a party.")
        return

    if target_key not in group["members"]:
        send_chat_status(session, f"{target_name} is not in your party.")
        return

    # Remove target from group
    state.remove_member(target_name)

    # Find target session (if online)
    target_sess = find_online_session(GS.all_sessions, target_name)

    send_chat_status(target_sess, "You have been removed from the party.") if target_sess else None
    send_chat_status(session, f"You removed {target_name} from the party.")

    # Refresh group after removal
    gid, group = state.get_group_for_name(session.current_character)

    if not group or len(group["members"]) <= 1:
        # Disband group (or leave single member alone)
        if group:
            # there is exactly one member left
            remaining_name = group["members"][0]
            remaining_sess = find_online_session(GS.all_sessions, remaining_name)

            state.disband_group(gid)

            if remaining_sess:
                remaining_sess.group_id = None
                remaining_sess.group_members = []
                remaining_sess.conn.sendall(build_empty_group_packet())


        if target_sess:
            target_sess.group_id = None
            target_sess.group_members = []
            target_sess.conn.sendall(build_empty_group_packet())

        return

    # Group still has >= 2 members
    members = online_group_members(group, GS.all_sessions)
    update_session_group_cache(gid, members)

    pkt = build_group_update_packet(members)
    for s, _ in members:
        try:
            s.conn.sendall(pkt)
        except:
            pass

    # Send empty packet to kicked target
    if target_sess:
        target_sess.group_id = None
        target_sess.group_members = []
        target_sess.conn.sendall(build_empty_group_packet())


def handle_group_leave(session, data):
    gid, group = get_group_for_session(session)
    if not group:
        send_chat_status(session, "You are not in a party.")
        return

    leaver_name = session.current_character

    # Remove leaving player
    state.remove_member(leaver_name)

    # Clear their legacy fields and send empty packet
    session.group_id = None
    session.group_members = []

    send_chat_status(session, "You left the party.")
    session.conn.sendall(build_empty_group_packet())

    # Refresh group after removal
    gid, group = state.get_group_for_name(leaver_name)

    # Check the group that the *remaining* members (if any) are in.
    # Use any remaining member if needed:
    remaining_gid = None
    remaining_group = None
    if not gid:
        # see if any online member still has a group
        for s in GS.all_sessions:
            if s is session:
                continue
            g2, grp2 = get_group_for_session(s)
            if grp2:
                remaining_gid = g2
                remaining_group = grp2
                break
    else:
        remaining_gid = gid
        remaining_group = group

    if not remaining_group or len(remaining_group["members"]) <= 1:
        # Disband / single leftover
        if remaining_group and remaining_gid is not None:
            names = remaining_group["members"][:]
            state.disband_group(remaining_gid)

            for name in names:
                s = find_online_session(GS.all_sessions, name)
                if not s:
                    continue
                s.group_id = None
                s.group_members = []
                s.conn.sendall(build_empty_group_packet())

        return

    # Party still has 2+ members
    members = online_group_members(remaining_group, GS.all_sessions)
    update_session_group_cache(remaining_gid, members)

    for m, _ in members:
        send_chat_status(m, f"{session.current_character} has left the party.")

    pkt = build_group_update_packet(members)
    for s, _ in members:
        s.conn.sendall(pkt)


def handle_group_leader(session, data):
    br = BitReader(data[4:])
    target_name = br.read_method_26()
    target_key = target_name.strip().lower()

    gid, group = get_group_for_session(session)
    if not group:
        send_chat_status(session, "You are not in a party.")
        return

    # Promote target
    state.set_leader(gid, target_name)

    # Notify members
    target_sess = find_online_session(GS.all_sessions, target_name)
    send_chat_status(session, f"You made {target_name} the party leader.")
    if target_sess:
        send_chat_status(target_sess, "You are now the party leader.")

    # Notify others
    gid, group = get_group_for_session(session)
    members = online_group_members(group, GS.all_sessions)
    for m, _ in members:
        if m not in (session, target_sess):
            send_chat_status(m, f"{target_name} is now the party leader.")

    # Rebuild group packet
    update_session_group_cache(gid, members)
    pkt = build_group_update_packet(members)

    for s, _ in members:
        s.conn.sendall(pkt)


def handle_send_group_chat(session, data):
    br = BitReader(data[4:])
    message = br.read_method_26()

    if not message.strip():
        return

    gid, group = get_group_for_session(session)
    if not group:
        send_chat_status(session, "You are not in a party.")
        return

    sender_name = session.current_character
    pkt = build_group_chat_packet(sender_name, message)
    print(f" [Group chat] {sender_name} Says : {message}")

    # Send to ALL ONLINE members including sender
    for m, _ in online_group_members(group, GS.all_sessions):
        m.conn.sendall(pkt)


def get_friend_name(friend_entry):
    if isinstance(friend_entry, dict):
        return friend_entry.get("name", "")
    return str(friend_entry)

def handle_friend_request(session, data):
    br = BitReader(data[4:])
    target_name = br.read_method_13()

    if target_name.lower() == session.current_character.lower():
        send_chat_status(session, "You cannot be friends with yourself.")
        return

    # 1. Update Sender's friend list
    sender_char = session.current_char_dict
    if "friends" not in sender_char:
        sender_char["friends"] = []
    
    # Check if already friend (handle both string and dict)
    already_friend = False
    for f in sender_char["friends"]:
        if get_friend_name(f).lower() == target_name.lower():
            already_friend = True
            break
            
    if not already_friend:
        sender_char["friends"].append(target_name)
    
    # Save sender
    save_characters(session.user_id, session.char_list)
    
    # 2. Update Target's friend list (Online or Offline)
    target_session = find_online_session(GS.all_sessions, target_name)
    
    if target_session:
        # ONLINE target
        target_char = target_session.current_char_dict
        if "friends" not in target_char:
            target_char["friends"] = []
        
        t_already = False
        for f in target_char["friends"]:
            if get_friend_name(f).lower() == session.current_character.lower():
                t_already = True
                break

        if not t_already:
            target_char["friends"].append(session.current_character)
            save_characters(target_session.user_id, target_session.char_list)
            
        send_chat_status(target_session, f"{session.current_character} added you as a friend.")
        send_chat_status(session, f"You are now friends with {target_name}.")
    
    else:
        # OFFLINE target
        t_uid, t_chars, t_char = find_user_by_character_name(target_name)
        if t_uid and t_char:
            if "friends" not in t_char:
                t_char["friends"] = []
            
            t_already = False
            for f in t_char["friends"]:
                if get_friend_name(f).lower() == session.current_character.lower():
                    t_already = True
                    break

            if not t_already:
                t_char["friends"].append(session.current_character)
                save_characters(t_uid, t_chars)
                
            send_chat_status(session, f"Added {target_name} to friends (offline).")
        else:
            send_chat_status(session, f"Could not find player {target_name}.")


def handle_request_friend_list(session, data):
    """
    Handles request for friend list (0xC9).
    Sends back 0xCA with the full list.
    Matching LinkUpdater.as/method_1827 and method_495.
    """
    friends = session.current_char_dict.get("friends", [])
    
    # Filter out empty entries
    valid_friends = []
    for f in friends:
        name = get_friend_name(f)
        if name:
            valid_friends.append(f)

    bb = BitBuffer(debug=False)
    
    # 0xCA starts with a count (method_4)
    bb.write_method_4(len(valid_friends))
    
    for friend_entry in valid_friends:
        friend_name = get_friend_name(friend_entry)
        
        # isRequest flag
        is_request = False
        if isinstance(friend_entry, dict):
            is_request = friend_entry.get("isRequest", False)
            
        # Check if online
        friend_sess = find_online_session(GS.all_sessions, friend_name)
        is_online = friend_sess is not None
                
        # Defaults
        level = 1
        class_id = 0
        char_name = friend_name
        
        if is_online:
            f_char = friend_sess.current_char_dict
            level = f_char.get("level", 1)
            c_name = f_char.get("class", "Paladin")
            class_id = {"Paladin": 0, "Rogue": 1, "Mage": 2}.get(c_name, 0)
            char_name = friend_sess.current_character or friend_name
        
        # Write friend entry (matching LinkUpdater method_495)
        bb.write_method_13(friend_name) # var_207 (Account name)
        bb.write_method_15(is_request)  # var_276 (Is friend request?)
        bb.write_method_15(is_online)   # bOnline
        
        if is_online:
            # param2.charName = param1.method_11() ? param1.method_13() : name;
            has_custom_char_name = (char_name != friend_name)
            bb.write_method_15(has_custom_char_name)
            if has_custom_char_name:
                bb.write_method_13(char_name)
                
            bb.write_method_6(class_id, Entity.const_244) # Class bits
            bb.write_method_6(level, Entity.MAX_CHAR_LEVEL_BITS) # Level bits

    payload = bb.to_bytes()
    session.conn.sendall(struct.pack(">HH", 0xCA, len(payload)) + payload)


def handle_request_visit_player_house(session, data):
    """
    Handles request to visit a player's house (0xF3).
    Reads target name, resolves their character data, and triggers teleport to CraftTown.
    """
    br = BitReader(data[4:])
    target_name = br.read_method_13()
    
    # 1. Resolve character data
    user_id, char_list, target_char = find_user_by_character_name(target_name)
    
    if not target_char:
        send_chat_status(session, f"Cannot find house for player {target_name}.")
        return
        
    # 2. Store target char for the level transfer handler
    # This will be picked up by level_config.py handle_level_transfer_request
    session.house_visit_char = target_char
    
    # 3. Trigger DO_TARGET for CraftTown
    # In level_config.py, door_id 999 is hardcoded to return to CraftTown
    bb = BitBuffer()
    bb.write_method_4(999) 
    bb.write_method_13("CraftTown")

    payload = bb.to_bytes()
    resp = struct.pack(">HH", 0x2E, len(payload)) + payload
    session.conn.sendall(resp)
    
    send_chat_status(session, f"Visiting {target_name}'s house...")