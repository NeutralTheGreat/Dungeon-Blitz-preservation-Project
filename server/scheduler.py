import glob
import json
import os
import random
import threading
import time
import heapq

from Character import save_characters, load_characters, CHAR_SAVE_DIR
from constants import class_111, class_16
from globals import send_skill_complete_packet, send_building_complete_packet, send_forge_reroll_packet, \
    send_talent_point_research_complete, all_sessions, build_hatchery_notify_packet, send_pet_training_complete, \
    send_egg_hatch_start

active_session_resolver = None

def is_ready(ready_ts: int) -> bool:
    return ready_ts and ready_ts <= int(time.time())

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

def _on_research_done_for(user_id: str, char_name: str):
    if not active_session_resolver:
        return

    session = active_session_resolver(user_id, char_name)
    if not (session and session.authenticated):
        return

    mem_char = next((c for c in session.char_list if c.get("name") == char_name), None)
    if not mem_char:
        return

    research = mem_char.get("SkillResearch")
    if not research:
        return

    if research.get("ReadyTime", 0) > int(time.time()):
        return  # not finished yet

    ability_id = research.get("abilityID")
    if ability_id:
        send_skill_complete_packet(session, ability_id)


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

    if bu.get("buildingID", 0) == 0:
        return
    if not is_ready(bu.get("ReadyTime", 0)):
        return

    building_id = bu.get("buildingID")
    new_rank    = bu.get("rank")

    mf = char.setdefault("magicForge", {})
    stats_dict = mf.setdefault("stats_by_building", {})
    if building_id and new_rank:
        stats_dict[str(building_id)] = new_rank

    char["buildingUpgrade"] = {
        "buildingID": 0,
        "rank": 0,
        "ReadyTime": 0
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

        send_building_complete_packet(session, building_id, new_rank)
        print(f"[{session.addr}] Sent building-complete (0xD8) ID={building_id}, rank={new_rank}")


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
    if not active_session_resolver:
        return

    session = active_session_resolver(user_id, char_name)
    if not (session and session.authenticated):
        return

    char = next(
        (c for c in session.char_list if c.get("name") == char_name),
        None
    )
    if not char:
        return

    tr = char.get("talentResearch")
    if not tr:
        return

    if tr.get("ReadyTime", 0) > int(time.time()):
        return

    send_talent_point_research_complete(session, tr.get("classIndex"))


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

    for sess in all_sessions:
        if sess.user_id == user_id and sess.current_character == char_name:
            sess.conn.sendall(build_hatchery_notify_packet())
            break

    # schedule next refresh
    next_time = int(time.time()) + class_16.new_egg_set_time
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
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chars = data.get("characters", [])
        dirty = False
        user_id = data.get("user_id")

        for char in chars:
            if not isinstance(char, dict):
                print(f"[SCHEDULER] Skipping invalid character entry: {char}")
                continue

            cname = char.get("name")

            # ─── Skill research ───
            sr = char.get("SkillResearch")
            if sr:
                rt = sr.get("ReadyTime", 0)
                if rt > now:
                    schedule_research(user_id, cname, rt)

            # ─── Building upgrade ───
            bu = char.get("buildingUpgrade", {})
            if isinstance(bu, dict):
                rt = bu.get("ReadyTime", 0)
                if bu.get("buildingID", 0) and rt > now:
                    schedule_building_upgrade(user_id, cname, rt)

            # ─── Magic forge ───
            mf = char.get("magicForge")
            if isinstance(mf, dict) and mf.get("hasSession") and mf.get("status") == class_111.const_286:
                rt = mf.get("ReadyTime", 0)
                if rt > now:
                    schedule_forge(
                        user_id,
                        cname,
                        rt,
                        mf.get("primary", 0),
                        mf.get("secondary", 0)
                    )
                else:
                    mf["hasSession"] = False
                    mf["status"] = class_111.const_264
                    dirty = True

            # ─── Talent research ───
            tr = char.get("talentResearch")
            if tr:
                rt = tr.get("ReadyTime", 0)
                if rt > now:
                    schedule_Talent_point_research(user_id, cname, rt)

            # ─── Egg rotation ───
            egg_rt = char.get("EggResetTime")
            if not egg_rt:
                char["EggResetTime"] = now + class_16.new_egg_set_time
                egg_rt = char["EggResetTime"]
                dirty = True

            schedule_hatchery_refresh(user_id, cname, egg_rt)

            # ─── Pet training ───
            tp = char.get("trainingPet", [])
            if tp:
                rt = tp[0].get("trainingTime", 0)
                if rt > now:
                    schedule_pet_training(user_id, cname, rt)

            # ─── Egg hatch ───
            egg = char.get("EggHachery")
            if egg:
                rt = egg.get("ReadyTime", 0)
                if rt > now:
                    schedule_egg_hatch(user_id, cname, rt)

        if dirty:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[SCHEDULER] Normalized {os.path.basename(path)}")
