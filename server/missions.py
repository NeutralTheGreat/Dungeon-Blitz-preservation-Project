import json
from typing import Optional, Dict
"""
 if a missions has "Achievement": "True", it means that this missions is a special mission 

"""
# cache
_MISSION_DEFS_BY_ID: Optional[Dict[int, dict]] = None
_MISSION_EXTRA_BY_ID: Optional[Dict[int, dict]] = None
_MISSION_MAX_ID: int = 0

def _is_truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1","true","yes","y","t")

def _parse_int(v, default=0) -> int:
    try:
        return int(v)
    except Exception:
        return default

def load_mission_defs(path: str = "data/MissionTypes.json") -> None:
    global _MISSION_DEFS_BY_ID, _MISSION_MAX_ID, _MISSION_EXTRA_BY_ID
    if _MISSION_DEFS_BY_ID is not None:
        return

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    defs: Dict[int, dict] = {}
    extra: Dict[int, dict] = {}
    max_id = 0

    for row in raw:
        mid = _parse_int(row.get("MissionID"))
        if mid <= 0:
            continue

        # existing fields (client-side flags)
        is_achievement = _is_truthy(row.get("Achievement"))
        complete_count = max(1, _parse_int(row.get("CompleteCount", 1)))
        is_timed = (
            _is_truthy(row.get("Timed"))
            or bool(row.get("Dungeon"))  # treat any Dungeon as timed/ranked
        )

        defs[mid] = {
            "id": mid,
            "Tier": is_achievement,
            "highscore": complete_count,
            "Time": is_timed,
        }

        # NEW: store NPC names and skit texts for dialogue lookup
        extra[mid] = {
            "ContactName": row.get("ContactName"),
            "ReturnName":  row.get("ReturnName"),
            "OfferText":   row.get("OfferText"),
            "ActiveText":  row.get("ActiveText"),
            "ReturnText":  row.get("ReturnText"),
            "PraiseText":  row.get("PraiseText"),
        }

        if mid > max_id:
            max_id = mid

    _MISSION_DEFS_BY_ID = defs
    _MISSION_EXTRA_BY_ID = extra
    _MISSION_MAX_ID = max_id

def get_mission_extra(mid: int) -> dict:
    if _MISSION_EXTRA_BY_ID is None:
        load_mission_defs()
    return (_MISSION_EXTRA_BY_ID or {}).get(mid, {})

def get_mission_def(mid: int) -> dict:
    # safe default: not achievement, not timed, count = 1
    base = {"id": mid, "Tier": False, "highscore": 1, "Time": False}
    if _MISSION_DEFS_BY_ID is None:
        load_mission_defs()
    return (_MISSION_DEFS_BY_ID or {}).get(mid, base)

def get_total_mission_defs() -> int:
    if _MISSION_DEFS_BY_ID is None:
        load_mission_defs()
    return _MISSION_MAX_ID
