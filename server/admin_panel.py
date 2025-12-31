from flask import Flask, render_template, request, jsonify
import json
import os
import struct
import inspect
import threading
import time

from BitBuffer import BitBuffer

# ──────────────────────────────────────────────────────────────
# Flask setup
# ──────────────────────────────────────────────────────────────

app = Flask(__name__)

DATA_FOLDER = "data"
PACKETS_FILE = os.path.join(DATA_FOLDER, "packet_types.json")

packet_loop_event = threading.Event()
sessions_getter = None  # injected by server.py

os.makedirs(DATA_FOLDER, exist_ok=True)

if not os.path.exists(PACKETS_FILE):
    with open(PACKETS_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4)

with open(PACKETS_FILE, "r", encoding="utf-8") as f:
    packets_data = json.load(f)

# ──────────────────────────────────────────────────────────────
# BitBuffer helpers
# ──────────────────────────────────────────────────────────────

BITBUFFER_METHODS = sorted(
    name
    for name, fn in inspect.getmembers(BitBuffer, predicate=inspect.isfunction)
    if name.startswith("write_")
)

def build_packet(method_calls, packet_type: int) -> bytes:
    """
    Build a full packet using BitBuffer calls.
    """
    bb = BitBuffer(debug=True)

    for method_name, args in method_calls:
        fn = getattr(bb, method_name, None)
        if not fn:
            raise ValueError(f"Unknown BitBuffer method: {method_name}")

        if isinstance(args, (list, tuple)):
            fn(*args)
        else:
            fn(args)

    payload = bb.to_bytes()
    header = struct.pack(">HH", packet_type, len(payload))
    return header + payload


def parse_args(raw: str):
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "." in part:
                out.append(float(part))
            else:
                out.append(int(part))
        except ValueError:
            out.append(part)
    return out[0] if len(out) == 1 else out

# ──────────────────────────────────────────────────────────────
# Routes – UI
# ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "admin_panel.html",
        saved_packets=list(packets_data.keys()),
        method_suggestions=BITBUFFER_METHODS,
    )

@app.route("/active_players", methods=["GET"])
def active_players():
    players = []
    for s in list(sessions_getter()):
        if getattr(s, "current_character", None):
            players.append(s.current_character)
    return jsonify(players)

# ──────────────────────────────────────────────────────────────
# Saved packet CRUD
# ──────────────────────────────────────────────────────────────

@app.route("/load_packet", methods=["POST"])
def load_packet():
    data = request.get_json()
    name = data.get("name")

    pkt = packets_data.get(name)
    if not pkt:
        return jsonify({"error": "Packet not found"}), 404

    return jsonify(pkt)

@app.route("/save_packet", methods=["POST"])
def save_packet():
    data = request.json
    name = data.get("name")

    if not name:
        return jsonify({"error": "Name required"}), 400

    packets_data[name] = {
        "packet_type": data["packet_type"],
        "description": data.get("description", ""),
        "buffers": data["buffers"],
    }

    with open(PACKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(packets_data, f, indent=4)

    return jsonify({
        "success": True,
        "saved_packets": list(packets_data.keys())
    })

@app.route("/delete_packet", methods=["POST"])
def delete_packet():
    name = request.json.get("name")
    if name not in packets_data:
        return jsonify({"error": "Packet not found"}), 404

    del packets_data[name]

    with open(PACKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(packets_data, f, indent=4)

    return jsonify({
        "success": True,
        "saved_packets": list(packets_data.keys())
    })

# ──────────────────────────────────────────────────────────────
# Packet sending
# ──────────────────────────────────────────────────────────────

@app.route("/send_packet", methods=["POST"])
def send_packet():
    data = request.json

    pkt_type = int(data["packet_type"], 16)
    target_name = data.get("target_player", "").strip().lower()
    delay = float(data.get("delay", 1))
    loop = data.get("loop", False)

    method_calls = []
    for row in data["buffers"]:
        method = row["method"].strip()
        value = row["value"].strip()
        if not method or not value:
            continue
        method_calls.append((method, parse_args(value)))

    if not method_calls:
        return jsonify({"error": "No buffer rows provided"}), 400

    packet = build_packet(method_calls, pkt_type)

    def send_once():
        count = 0
        for sess in list(sessions_getter()):
            if target_name and sess.current_character.lower() != target_name:
                continue
            try:
                sess.conn.sendall(packet)
                count += 1
            except Exception:
                pass
        return count

    if not loop:
        sent = send_once()
        return jsonify({
            "success": True,
            "message": f"Packet 0x{pkt_type:X} sent to {sent} client(s)"
        })

    packet_loop_event.clear()

    def loop_send():
        while not packet_loop_event.is_set():
            send_once()
            time.sleep(delay)

    threading.Thread(target=loop_send, daemon=True).start()

    return jsonify({
        "success": True,
        "message": "Packet loop started"
    })

@app.route("/stop_packet_loop", methods=["POST"])
def stop_packet_loop():
    packet_loop_event.set()
    return jsonify({
        "success": True,
        "message": "Packet loop stopped"
    })

def run_admin_panel(get_sessions, port=5000):
    global sessions_getter
    sessions_getter = get_sessions
    app.run(
        host="127.0.0.1",
        port=port,
        debug=True,
        use_reloader=False
    )
