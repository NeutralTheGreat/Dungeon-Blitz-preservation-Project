import math
import time
import threading
import struct
from BitBuffer import BitBuffer
from globals import GS, send_hp_update, get_npc_props
from combat import apply_and_broadcast_hp_delta

#AI now enabled for server-side enemy control
AI_ENABLED = True

AI_INTERVAL = 0.125
TIMESTEP = 1 / 60.0
AGGRO_RADIUS = 400
MAX_SPEED = 400.0  # Reduced from 1200 for less sliding
ACCELERATION = 40.0
FRICTION = 0.85     # Increased friction (0-1 multiplier approach or constant subtraction)
STOP_DISTANCE = 50
ATTACK_RANGE = 90
ATTACK_COOLDOWN = 1.5  # seconds between attacks
BASE_NPC_DAMAGE = 15  # base damage for NPC attacks

# ─────────────── Core helpers ───────────────
def get_pos(ent):
    """Get position from entity, checking both x/y and pos_x/pos_y"""
    x = ent.get("pos_x", ent.get("x", 0.0))
    y = ent.get("pos_y", ent.get("y", 0.0))
    return x, y

def distance(a, b):
    ax, ay = get_pos(a)
    bx, by = get_pos(b)
    return math.hypot(ax - bx, ay - by)

def update_npc_physics(npc, dt=TIMESTEP, steps=18):
    vx = npc.get("velocity_x", 0.0)
    vy = npc.get("velocity_y", 0.0)
    
    # Simple friction/damping
    vx *= FRICTION
    vy *= FRICTION
    
    # Stop if very slow
    if abs(vx) < 1.0: vx = 0
    if abs(vy) < 1.0: vy = 0

    npc["pos_x"] += vx * dt * steps
    npc["pos_y"] += vy * dt * steps
    npc["x"] = npc["pos_x"]
    npc["y"] = npc["pos_y"]
    npc["velocity_x"] = vx
    npc["velocity_y"] = vy

def broadcast_npc_move(npc, level_name, delta_x, delta_y, delta_vx):
    recipients = [s for s in GS.all_sessions if s.player_spawned and s.current_level == level_name]

    bb = BitBuffer()
    bb.write_method_4(npc["id"])
    bb.write_method_45(int(delta_x))
    bb.write_method_45(int(delta_y))
    bb.write_method_45(int(delta_vx))
    bb.write_method_6(0, 2)
    bb.write_method_15(npc.get("b_left", False))
    bb.write_method_15(npc.get("b_running", False))
    
    # Try setting the 3rd flag for 'Attacking' (or 'Active') state
    is_attacking = npc.get("brain_state") == "attacking"
    bb.write_method_15(is_attacking) 
    
    bb.write_method_15(False)
    bb.write_method_15(False)
    bb.write_method_15(False)

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x07, len(payload)) + payload

    for s in recipients:
        try:
            s.conn.sendall(pkt)
        except Exception as e:
            print(f"    ✗ {s.addr}: {e}")


def broadcast_remove_buff(entity_id, buff_type_id, instance_id, level_name):
    recipients = [s for s in GS.all_sessions if s.player_spawned and s.current_level == level_name]
    
    bb = BitBuffer(debug=False)
    bb.write_method_9(entity_id)
    bb.write_method_9(buff_type_id)
    bb.write_method_9(instance_id)
    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x0C, len(payload)) + payload

    for s in recipients:
        try:
            s.conn.sendall(pkt)
        except Exception as e:
            print(f"[AI Buff] Error sending buff remove to {s.addr}: {e}")

def broadcast_npc_attack(npc, target_player, level_name, damage):
    """Broadcast NPC attack: power cast + power hit packets"""
    recipients = [s for s in GS.all_sessions if s.player_spawned and s.current_level == level_name]
    
    npc_id = npc["id"]
    target_id = target_player.get("id")
    power_id = npc.get("power_id", 1)  # Default power ID
    if power_id == 0: power_id = 2     # Fallback if config has 0
    
    print(f"[AI Attack] NPC ID:{npc_id} targeting Player ID:{target_id}, damage:{damage}, recipients:{len(recipients)}")
    
    # Build power cast packet (0x2B)
    bb_cast = BitBuffer(debug=False)
    bb_cast.write_method_4(npc_id)
    bb_cast.write_method_4(power_id)
    bb_cast.write_method_15(False)  # has_target_entity
    bb_cast.write_method_15(True)   # has_target_pos
    tx, ty = get_pos(target_player)
    bb_cast.write_method_24(int(tx))
    bb_cast.write_method_24(int(ty))
    bb_cast.write_method_15(False)  # has_projectile
    bb_cast.write_method_15(False)  # is_charged
    bb_cast.write_method_15(False)  # has_extra
    bb_cast.write_method_15(False)  # has_flags
    
    cast_payload = bb_cast.to_bytes()
    cast_pkt = struct.pack(">HH", 0x2B, len(cast_payload)) + cast_payload
    
    # Build power hit packet (0x2A)
    bb_hit = BitBuffer(debug=False)
    bb_hit.write_method_4(target_id)
    bb_hit.write_method_4(npc_id)
    bb_hit.write_method_24(damage)
    bb_hit.write_method_4(power_id)
    
    # Let client handle animation based on power_id (reverted override)
    # If this fails, we can try other overrides later
    bb_hit.write_method_15(False)   # has_animation_override
    # bb_hit.write_method_9(1)      
    
    bb_hit.write_method_15(False)  # has_effect_override
    bb_hit.write_method_15(False)  # is_critical
    
    hit_payload = bb_hit.to_bytes()
    hit_pkt = struct.pack(">HH", 0x2A, len(hit_payload)) + hit_payload
    
    print(f"[AI Attack] Sending cast packet (0x2B, {len(cast_payload)} bytes) and hit packet (0x2A, {len(hit_payload)} bytes)")
    
    # Send to all clients
    for s in recipients:
        try:
            s.conn.sendall(cast_pkt)
            s.conn.sendall(hit_pkt)
            print(f"[AI Attack] Sent to {s.addr}")
        except Exception as e:
            print(f"[AI Attack] Error sending to {s.addr}: {e}")
            
    # FORCE DAMAGE UPDATE (Server-side authoritative)
    if damage > 0 and target_id and "session" in target_player:
        t_session = target_player["session"]
        # Update HP in entity
        current_hp = target_player.get("hp", 100)
        new_hp = max(0, current_hp - damage)
        target_player["hp"] = new_hp
        
        # Also update the session's entity copy if different
        if t_session and t_session.entities.get(target_id):
            t_session.entities[target_id]["hp"] = new_hp

        print(f"[AI Attack] Applying {damage} dmg to Player {target_id}. HP: {current_hp} -> {new_hp}")
        
        # Send 0x3A Health Update
        apply_and_broadcast_hp_delta(
            source_session=target_player["session"],
            ent_id=target_id,
            delta=-damage,
            all_sessions=GS.all_sessions,  # Ideally filter by level
            source_name="NPC_Attack"
        )
        # Also notify the target's own client (apply_and_broadcast_hp_delta skips source_session)
        send_hp_update(t_session, target_id, -damage)


# ───────────────── AI loop per level ─────────────────
def run_ai_loop(level_name):
    """Threaded loop driving NPC AI + physics for one level."""
    print(f"[AI] Starting AI loop for level: {level_name}")

    while True:
        time.sleep(AI_INTERVAL)
        current_time = time.time()

        level_map = GS.level_entities.get(level_name, {})

        npcs = [
            ent["props"]
            for ent in level_map.values()
            if ent["kind"] == "npc" and ent["props"].get("team", 0) == 2  # Only team 2 enemies
        ]

        # Get players directly from sessions (more reliable than level_entities)
        players = []
        for session in GS.all_sessions:
            if session.player_spawned and session.current_level == level_name and session.clientEntID:
                # Get player entity from session's entities dict
                player_ent = session.entities.get(session.clientEntID)
                if player_ent:
                    players.append({
                        "id": session.clientEntID,
                        "x": player_ent.get("x", player_ent.get("pos_x", 0)),
                        "y": player_ent.get("y", player_ent.get("pos_y", 0)),
                        "pos_x": player_ent.get("x", player_ent.get("pos_x", 0)),
                        "pos_y": player_ent.get("y", player_ent.get("pos_y", 0)),
                        "dead": player_ent.get("dead", False),
                        "hp": player_ent.get("hp", 100),
                        "session": session
                    })

        if not npcs:
            continue
            
        if not players:
            continue

        # Debug: Log first iteration per level
        log_key = f'_logged_{level_name}'
        if not hasattr(run_ai_loop, log_key):
            print(f"[AI] Found {len(npcs)} NPCs and {len(players)} players in {level_name}")
            if npcs:
                npc = npcs[0]
                print(f"[AI] Sample NPC: id={npc.get('id')}, name={npc.get('name')}, x={npc.get('x')}, y={npc.get('y')}")
            if players:
                player = players[0]
                print(f"[AI] Sample Player: id={player.get('id')}, x={player.get('x')}, y={player.get('y')}")
            setattr(run_ai_loop, log_key, True)

        for npc in npcs:
            # Skip dead NPCs
            if npc.get("hp", 1) <= 0 or npc.get("dead", False):
                continue
            
            # Expire buffs for server NPCs
            buffs = npc.setdefault("buffs", [])
            if buffs:
                remaining_buffs = []
                for buff in buffs:
                    if buff.get("expires_at", 0) <= current_time:
                        broadcast_remove_buff(npc["id"], buff.get("buff_type_id", 0), buff.get("instance_id", 0), level_name)
                    else:
                        remaining_buffs.append(buff)
                if len(remaining_buffs) != len(buffs):
                    npc["buffs"] = remaining_buffs

            npc["pos_x"] = npc.get("pos_x", npc.get("x", 0.0))
            npc["pos_y"] = npc.get("pos_y", npc.get("y", 0.0))

            # Find nearest player
            closest, closest_dist = None, AGGRO_RADIUS + 1
            for p in players:
                # Skip dead players
                if p.get("dead", False) or p.get("hp", 1) <= 0:
                    continue
                d = distance(npc, p)
                if d < closest_dist:
                    closest, closest_dist = p, d

            # Save last position for delta calc
            last_x = npc.get("var_959", npc["pos_x"])
            last_y = npc.get("var_874", npc["pos_y"])
            last_vx = npc.get("var_1258", 0)

            if closest:
                # In attack range - stop and attack
                if closest_dist <= ATTACK_RANGE:
                    npc["b_running"] = False
                    npc["velocity_x"] = 0
                    npc["velocity_y"] = 0
                    npc["b_left"] = closest["pos_x"] < npc["pos_x"] if "pos_x" in closest else closest.get("x", 0) < npc["pos_x"]
                    npc["brain_state"] = "attacking"
                    
                    # Check attack cooldown
                    last_attack = npc.get("last_attack_time", 0)
                    if current_time - last_attack >= ATTACK_COOLDOWN:
                        npc["last_attack_time"] = current_time
                        # Calculate damage based on NPC level
                        npc_level = npc.get("level", 1)
                        damage = BASE_NPC_DAMAGE + (npc_level * 2)
                        
                        print(f"[AI] {npc.get('name', npc.get('id'))} attacking player at distance {closest_dist:.1f}")
                        broadcast_npc_attack(npc, closest, level_name, damage)
                    
                    broadcast_npc_move(npc, level_name, 0, 0, 0)
                    continue

                # In aggro range but not attack range - chase
                elif closest_dist <= AGGRO_RADIUS:
                    npc["b_running"] = True
                    cx = closest.get("pos_x", closest.get("x", 0))
                    cy = closest.get("pos_y", closest.get("y", 0))
                    
                    dx = cx - npc["pos_x"]
                    dy = cy - npc["pos_y"]
                    
                    # Normalize and apply speed
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        speed = MAX_SPEED
                        if dist < STOP_DISTANCE:
                            speed = speed * (dist / STOP_DISTANCE)
                            
                        npc["velocity_x"] = (dx / dist) * speed
                        npc["velocity_y"] = (dy / dist) * speed
                    
                    npc["b_left"] = dx < 0
                    npc["brain_state"] = "chasing"
                else:
                    npc["b_running"] = False
                    npc["brain_state"] = "idle"
            else:
                npc["b_running"] = False
                npc["brain_state"] = "idle"

            update_npc_physics(npc, steps=int(AI_INTERVAL / TIMESTEP))

            # Compute new deltas for packet
            delta_x = int(npc["pos_x"] - last_x)
            delta_y = int(npc["pos_y"] - last_y)
            delta_vx = int(npc["velocity_x"] - last_vx)

            npc["var_959"] = npc["pos_x"]
            npc["var_874"] = npc["pos_y"]
            npc["var_1258"] = npc["velocity_x"]

            if delta_x or delta_y or delta_vx:
                broadcast_npc_move(npc, level_name, delta_x, delta_y, delta_vx)

# ─────────────── Thread management ───────────────

_active_ai_threads = {}

def ensure_ai_loop(level_name, run_func=run_ai_loop):
    """Start one AI thread per level (safe to call repeatedly)."""
    if not level_name or level_name in _active_ai_threads:
        return
    t = threading.Thread(target=run_func, args=(level_name,), daemon=True)
    t.start()
    _active_ai_threads[level_name] = t
    print(f"[AI] Started NPC AI thread for level '{level_name}'")
