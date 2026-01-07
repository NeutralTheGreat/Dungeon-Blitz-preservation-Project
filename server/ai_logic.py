import math
import time
import threading
import struct
from BitBuffer import BitBuffer
from globals import GS

#AI needs a lot more work to be done so will keep it off for now
AI_ENABLED = False

AI_INTERVAL = 0.125
TIMESTEP = 1 / 60.0
AGGRO_RADIUS = 250
MAX_SPEED = 1200.0
ACCELERATION = 50.0
FRICTION = 1.0
STOP_DISTANCE = 50

# ─────────────── Core helpers ───────────────
def distance(a, b):
    dx = a.get("pos_x", 0.0) - b.get("pos_x", 0.0)
    dy = a.get("pos_y", 0.0) - b.get("pos_y", 0.0)
    return math.hypot(dx, dy)

def update_npc_physics(npc, dt=TIMESTEP, steps=18):
    vx = npc.get("velocity_x", 0.0)
    vy = npc.get("velocity_y", 0.0)
    left  = npc.get("b_left", False)
    run   = npc.get("b_running", False)

    # accelerate or friction
    if run:
        accel = ACCELERATION
        vx = max(vx - accel, -MAX_SPEED) if left else min(vx + accel, MAX_SPEED)
    else:
        if abs(vx) > FRICTION:
            vx -= FRICTION * math.copysign(1, vx)
        else:
            vx = 0.0

    # integrate over multiple physics frames per AI tick
    npc["pos_x"] += vx * dt * steps
    npc["velocity_x"] = vx

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
    bb.write_method_15(False)
    bb.write_method_15(False)
    bb.write_method_15(False)
    bb.write_method_15(False)

    payload = bb.to_bytes()
    pkt = struct.pack(">HH", 0x07, len(payload)) + payload

    #print(f"[AI] Broadcasting NPC {npc['id']} move ({len(recipients)} clients)")
    for s in recipients:
        try:
            s.conn.sendall(pkt)
            #print(f"    → sent to {s.addr}")
        except Exception as e:
            print(f"    ✗ {s.addr}: {e}")

# ─────────────── AI loop per level ───────────────
def run_ai_loop(level_name):
    """Threaded loop driving NPC AI + physics for one level."""
    #print(f"[AI] Starting loop for level {level_name}")

    while True:
        time.sleep(AI_INTERVAL)

        npcs = GS.level_npcs.get(level_name, {})
        sessions = list(GS.level_registry.get(level_name, []))
        players = GS.level_players.get(level_name, [])

        if not npcs or not players:
            continue

        for npc in npcs.values():
            npc["pos_x"] = npc.get("pos_x", npc.get("x", 0.0))
            npc["pos_y"] = npc.get("pos_y", npc.get("y", 0.0))

            # Find nearest player
            closest, closest_dist = None, AGGRO_RADIUS + 1
            for p in players:
                d = distance(npc, p)
                if d < closest_dist:
                    closest, closest_dist = p, d

            # Save last position for delta calc
            last_x = npc.get("var_959", npc["pos_x"])
            last_y = npc.get("var_874", npc["pos_y"])
            last_vx = npc.get("var_1258", 0)

            if closest:
                if closest_dist <= STOP_DISTANCE:
                    # Stop moving
                    npc["b_running"] = False
                    npc["brain_state"] = "idle"
                    npc["velocity_x"] = 0

                    # when the NPC reaches, the player server sends this to stop the NPC from moving
                    broadcast_npc_move(
                        npc,
                        level_name,
                        delta_x=0,
                        delta_y=0,
                        delta_vx=0
                    )
                    broadcast_npc_move(npc, level_name, 0, 0, 0)
                    continue

                elif closest_dist <= AGGRO_RADIUS:
                    npc["b_running"] = True
                    npc["b_left"] = closest["pos_x"] < npc["pos_x"]
                    npc["brain_state"] = "chasing"
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

            if delta_x or delta_y:
                #print(f"[AI] NPC {npc['id']} Δx={delta_x:.2f} vx={npc['velocity_x']:.2f}")
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
    #print(f"[AI] Started NPC logic thread for level '{level_name}'")
