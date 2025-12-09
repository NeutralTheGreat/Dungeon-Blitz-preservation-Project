import glob
import json
import os
import random
import threading
import time
import heapq
import struct

from BitBuffer import BitBuffer
from Character import save_characters, load_characters, CHAR_SAVE_DIR
from constants import class_111, class_64_const_218, class_1
from globals import send_skill_complete_packet, send_building_complete_packet, send_forge_reroll_packet, \
    send_talent_point_research_complete, all_sessions, build_hatchery_notify_packet, send_pet_training_complete, \
    send_egg_hatch_start

active_session_resolver = None

def set_active_session_resolver(fn):
    """
    fn(user_id: str, char_name: str) -> ClientSession or None
    """
    global active_session_resolver
    active_session_resolver = fn

class TaskScheduler:
    def __init__(self):
        self._lock = threading.Lock()
        self._queue = []
        self._next_id = 0
        self._new_event = threading.Event()
        threading.Thread(target=self._run_loop, daemon=True).start()

    def schedule(self, run_at: int, callback: callable):
        with self._lock:
            heapq.heappush(self._queue, (run_at, self._next_id, callback))
            self._next_id += 1
            self._new_event.set()

    def _run_loop(self):
        while True:
            with self._lock:
                if not self._queue:
                    timeout = None
                else:
                    run_at, _, _ = self._queue[0]
                    timeout = max(0, run_at - int(time.time()))
            self._new_event.wait(timeout=timeout)
            self._new_event.clear()

            now = int(time.time())
            to_run = []
            with self._lock:
                while self._queue and self._queue[0][0] <= now:
                    _, _, cb = heapq.heappop(self._queue)
                    to_run.append(cb)
            for cb in to_run:
                try:
                    cb()
                except Exception as e:
                    print(f"[Scheduler] callback error: {e}")

scheduler = TaskScheduler()

def reschedule_for_session(session):
    now = int(time.time())
    for char in session.char_list:
        research = char.get("SkillResearch")
        if not research:
            continue

        ready_ts = research.get("ReadyTime", 0)
        is_done = research.get("done", False)

        if ready_ts <= now:
            if not is_done:
                research["done"] = True
                save_characters(session.user_id, session.char_list)
                print(f"[{session.addr}] Offline research marked done …")

                bb = BitBuffer()
                bb.write_method_6(research["abilityID"], 7)
                payload = bb.to_bytes()
                session.conn.sendall(struct.pack(">HH", 0xC0, len(payload)) + payload)
                print(f"[{session.addr}] Sent research-complete on login abilityID={research['abilityID']}")
        else:
            scheduler.schedule(
                run_at=ready_ts,
                callback=lambda uid=session.user_id, cname=char["name"]: _on_research_done_for(uid, cname)
            )

def _on_research_done_for(user_id: str, char_name: str):
    chars = load_characters(user_id)
    char = next((c for c in chars if c.get("name") == char_name), None)
    if not char or "SkillResearch" not in char:
        return
    research = char["SkillResearch"]
    if research.get("done", False):
        return
    research["done"] = True
    save_characters(user_id, chars)

    if active_session_resolver:
        session = active_session_resolver(user_id, char_name)
        if session and session.authenticated:
            mem_char = next((c for c in session.char_list if c.get("name") == char_name), None)
            if mem_char and "SkillResearch" in mem_char:
                mem_char["SkillResearch"]["done"] = True
            try:
                send_skill_complete_packet(session, research["abilityID"])
            except Exception as e:
                print(f"[Scheduler] notify failed: {e}")

def schedule_research(user_id: str, char_name: str, ready_ts: int):
    handle = scheduler.schedule(
        run_at=ready_ts,
        callback=lambda uid=user_id, cn=char_name: _on_research_done_for(uid, cn)
    )
    return handle

def _on_building_done_for(user_id: str, char_name: str):
    chars = load_characters(user_id)
    char = next((c for c in chars if c.get("name") == char_name), None)
    if not char:
        return

    bu = char.get("buildingUpgrade", {})
    if not isinstance(bu, dict):
        return

    now = int(time.time())
    if bu.get("buildingID", 0) == 0:
        return
    if bu.get("done") or bu.get("ReadyTime", 0) > now:
        return

    building_id = bu.get("buildingID")
    new_rank    = bu.get("rank")

    bu["done"] = True
    mf = char.setdefault("magicForge", {})
    stats_dict = mf.setdefault("stats_by_building", {})
    if building_id and new_rank:
        stats_dict[str(building_id)] = new_rank

    char["buildingUpgrade"] = {
        "buildingID": 0,
        "rank": 0,
        "ReadyTime": 0,
        "done": False,
    }
    save_characters(user_id, chars)

    if not active_session_resolver:
        return
    session = active_session_resolver(user_id, char_name)
    if not (session and session.authenticated):
        return

    mem_char = next((c for c in session.char_list if c.get("name") == char_name), None)
    if mem_char:
        mem_mf = mem_char.setdefault("magicForge", {})
        mem_stats = mem_mf.setdefault("stats_by_building", {})
        if building_id and new_rank:
            mem_stats[str(building_id)] = new_rank
        mem_char["buildingUpgrade"] = char["buildingUpgrade"].copy()

    try:
        send_building_complete_packet(session, building_id, new_rank)
        print(f"[{session.addr}] Sent building-complete (0xD8) ID={building_id}, rank={new_rank}")
    except Exception as e:
        print(f"[Scheduler] building notify failed: {e}")

def schedule_building_upgrade(user_id: str, char_name: str, ready_ts: int):
    handle = scheduler.schedule(
        run_at=ready_ts,
        callback=lambda uid=user_id, cn=char_name: _on_building_done_for(uid, cn)
    )
    return handle

def _on_forge_done_for(user_id: str, char_name: str, primary: int, secondary: int):
    chars = load_characters(user_id)
    char = next((c for c in chars if c.get("name") == char_name), None)
    if not char or "magicForge" not in char:
        return

    mf = char["magicForge"]
    forge_roll_a = random.randint(0, 65535)
    forge_roll_b = random.randint(0, 65535)
    tier = 1 if secondary else 0
    usedlist = mf.get("usedlist", 0)
    mf.update({
        "hasSession": False,
        "status": class_111.const_264,
        "ReadyTime": 0,
        "forge_roll_a": forge_roll_a,
        "forge_roll_b": forge_roll_b,
        "secondary": secondary,
        "secondary_tier": tier,
        "usedlist": usedlist
    })
    save_characters(user_id, chars)
    if active_session_resolver:
        session = active_session_resolver(user_id, char_name)
        if session and session.authenticated:

            mem_char = next((c for c in session.char_list if c.get("name") == char_name), None)
            if mem_char:
                mem_mf = mem_char.setdefault("magicForge", {})
                mem_mf.update(mf)

            send_forge_reroll_packet(
                session=session,
                primary=primary,
                roll_a=forge_roll_a,
                roll_b=forge_roll_b,
                tier=tier,
                secondary=secondary,
                usedlist=usedlist,
                action="charm craft complete"
            )
            print(f"[{session.addr}] Sent forge-complete packet → primary={primary}, secondary={secondary}, tier={tier}")

def schedule_forge(user_id: str, char_name: str, run_at: int, primary: int, secondary: int):
    scheduler.schedule(
        run_at=run_at,
        callback=lambda uid=user_id, cn=char_name, p=primary, s=secondary:
            _on_forge_done_for(uid, cn, p, s)
    )

def _on_talent_done_for(user_id: str, char_name: str):
    chars = load_characters(user_id)
    char = next((c for c in chars if c.get("name") == char_name), None)
    if not char:
        return

    tr = char.get("talentResearch", {})
    now = int(time.time())
    if tr.get("done") or tr.get("ReadyTime", 0) > now:
        return

    tr["done"] = True
    save_characters(user_id, chars)

    if not active_session_resolver:
        return
    session = active_session_resolver(user_id, char_name)
    if not (session and session.authenticated):
        return

    mem_char = next((c for c in session.char_list if c.get("name") == char_name), None)
    if mem_char:
        mem_char["talentResearch"] = tr.copy()

    send_talent_point_research_complete(session, tr.get("classIndex"))
    print(f"[{session.addr}] Sent 0xD5 research complete for classIndex={tr.get('classIndex')}")

def schedule_Talent_point_research(user_id: str, char_name: str, run_at: int):
    handle = scheduler.schedule(
        run_at=run_at,
        callback=lambda uid=user_id, cn=char_name: _on_talent_done_for(uid, cn)
    )
    return handle

def _on_hatchery_refresh(user_id: str, char_name: str):
    chars = load_characters(user_id)
    char = next((c for c in chars if c["name"] == char_name), None)
    if not char:
        return

    # Skip notification if already sent
    if char.get("EggNotifySent", False):
         pass
    else:
        # Try to find online session
        for sess in all_sessions:
            if sess.user_id == user_id and sess.current_character == char_name:
                pkt = build_hatchery_notify_packet()
                sess.conn.sendall(pkt)
                break

        char["EggNotifySent"] = True
        save_characters(user_id, chars)

    # schedule next refresh
    next_time = int(time.time()) + 86400
    scheduler.schedule(next_time, lambda: _on_hatchery_refresh(user_id, char_name))


def schedule_hatchery_refresh(user_id: str, char_name: str, run_at: int):
    scheduler.schedule(run_at, lambda: _on_hatchery_refresh(user_id, char_name))

def _on_pet_training_done(user_id: str, char_name: str):
    chars = load_characters(user_id)
    char = next((c for c in chars if c.get("name") == char_name), None)
    if not char:
        return

    tp_list = char.get("trainingPet", [])
    if not tp_list:
        return

    ready_ts = tp_list[0].get("trainingTime", 0)
    now = int(time.time())

    if ready_ts > now:
        return  # not ready

    save_characters(user_id, chars)

    if active_session_resolver:
        session = active_session_resolver(user_id, char_name)
        if session and session.authenticated:
            pet_type = tp_list[0]["typeID"]
            send_pet_training_complete(session, pet_type)

def schedule_pet_training(user_id: str, char_name: str, ready_ts: int):
    scheduler.schedule(run_at=ready_ts,callback=lambda uid=user_id, cn=char_name:_on_pet_training_done(uid, cn))

def _on_egg_hatch_done(user_id: str, char_name: str):
    chars = load_characters(user_id)
    char = next((c for c in chars if c.get("name") == char_name), None)
    if not char:
        return

    egg = char.get("EggHachery")
    if not egg or egg.get("EggID", 0) == 0:
        return

    ready_ts = egg.get("ReadyTime", 0)
    now = int(time.time())

    # Still not finished? (scheduler may fire early)
    if ready_ts > now:
        return
    save_characters(user_id, chars)

    # Notify if the player is online
    if active_session_resolver:
        session = active_session_resolver(user_id, char_name)
        if session and session.authenticated:
           send_egg_hatch_start(session)


def schedule_egg_hatch(user_id: str, char_name: str, ready_ts: int):
    scheduler.schedule(run_at=ready_ts,callback=lambda uid=user_id, cn=char_name:_on_egg_hatch_done(uid, cn))

def boot_scan_all_saves():
    now = int(time.time())
    for path in glob.glob(os.path.join(CHAR_SAVE_DIR, "*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        chars = data.get("characters", [])
        dirty = False
        user_id = data.get("user_id")

        for char in chars:
            if not isinstance(char, dict):
                print(f"[SCHEDULER] Skipping invalid character entry: {char}")
                continue

            research = char.get("SkillResearch")
            if research and not research.get("done", False):
                rt = research.get("ReadyTime", 0)
                if rt <= now:
                    research["done"] = True
                    dirty = True
                else:
                    schedule_research(user_id, char["name"], rt)

            bu = char.get("buildingUpgrade")
            entries = []
            if isinstance(bu, dict):
                entries = [bu]
            elif isinstance(bu, list):
                entries = bu

            for upgrade in entries:
                if not upgrade.get("done", False):
                    rt = upgrade.get("ReadyTime", 0)
                    if rt <= now:
                        upgrade["done"] = True
                        dirty = True
                    else:
                        schedule_building_upgrade(user_id, char["name"], rt)

            mf = char.get("magicForge")
            if isinstance(mf, dict) and mf.get("hasSession") and mf.get("status") == class_111.const_286:
                ready_ts = mf.get("ReadyTime", 0)  # already epoch
                if ready_ts <= now:
                    # mark completed immediately
                    mf["hasSession"] = False
                    mf["status"] = class_111.const_264
                    dirty = True
                else:
                    schedule_forge(user_id, char["name"], ready_ts, mf.get("primary", 0), mf.get("secondary", 0))

            tr = char.get("talentResearch", {})
            if tr and not tr.get("done", False):
                rt = tr.get("ReadyTime", 0)
                if rt <= now:
                    # expired: mark done immediately
                    tr["done"] = True
                    dirty = True
                else:
                    # still pending: schedule its completion
                    schedule_Talent_point_research(user_id, char["name"], rt)

            egg_rt = char.get("EggResetTime")

            if not egg_rt:
                egg_rt = int(time.time()) + 86400
                char["EggResetTime"] = egg_rt
                dirty = True

            schedule_hatchery_refresh(user_id, char["name"], egg_rt)

            tp_list = char.get("trainingPet", [])
            if tp_list:
                ts = tp_list[0].get("trainingTime", 0)

                if ts <= now:

                    dirty = True
                else:
                    schedule_pet_training(user_id, char["name"], ts)

            egg_ht = char.get("EggHachery")
            if egg_ht:
                rt = egg_ht.get("ReadyTime", 0)
                if rt <= now:
                    pass
                else:
                    schedule_egg_hatch(user_id, char["name"], rt)

        if dirty:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Boot scan: patched expired timers in {os.path.basename(path)}")

boot_scan_all_saves()