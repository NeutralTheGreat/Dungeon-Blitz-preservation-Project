
from Character import handle_request_armory_gears, handle_alert_state_update, PaperDoll_Request, handle_change_look, \
    handle_apply_dyes
from dev import DEVFLAG_MASTER_CLIENT, handle_quest_progress_update, handle_level_state, handle_play_sound, \
    handle_action_update, handle_emote, handle_room_state_update, handle_room_event_start, handle_room_info_update, \
    handle_set_untargetable, handle_room_close, handle_room_unlock, handle_room_boss_info, handle_emote_end
from entity import handle_entity_full_update
from globals import Client_Crash_Reports

from Commands import handle_badge_request, handle_linkupdater, handle_talk_to_npc, handle_lockbox_reward, \
    handle_queue_potion, handle_hp_increase_notice, handle_grant_reward, handle_power_use, handle_pickup_lootdrop, \
    handle_set_level_complete, handle_send_combat_stats, handle_dungeon_run_report
from Forge import handle_start_forge, handle_forge_speed_up_packet, handle_collect_forge_charm, handle_cancel_forge, handle_use_forge_xp_consumable, handle_allocate_magic_forge_artisan_skill_points, handle_magic_forge_reroll
from buildings import handle_building_upgrade, handle_building_speed_up_request, handle_cancel_building_upgrade, handle_building_claim
from combat import handle_entity_destroy, handle_buff_tick_dot, handle_respawn_broadcast, handle_request_respawn, handle_power_hit, handle_projectile_explode, handle_add_buff, handle_remove_buff, handle_change_max_speed, handle_power_cast, handle_change_offset_y, handle_char_regen, handle_char_regen_tick, handle_equip_rune, handle_update_equipment, handle_update_single_gear, handle_create_gearset, handle_name_gearset, handle_update_gearset
from level_config import handle_open_door, handle_level_transfer_request, handle_request_door_state, handle_entity_incremental_update
from login import handle_login_version, handle_login_create, handle_login_authenticate, handle_login_character_create, handle_character_select, handle_gameserver_login
from pets import handle_equip_pets, handle_mount_equip_packet, handle_request_hatchery_eggs, handle_train_pet, handle_pet_training_collect, handle_pet_training_cancel, handle_pet_speed_up, handle_egg_hatch, handle_egg_speed_up, handle_collect_hatched_egg, handle_cancel_egg_hatch
from skills import handle_skill_trained_claim, handle_skill_research_cancel_request, handle_skill_speed_up_request, handle_start_skill_training, handle_equip_active_skills
from socials import handle_zone_panel_request, handle_public_chat, handle_private_message, handle_room_thought, handle_start_skit, handle_emote_begin, handle_group_invite, handle_query_message_answer, handle_map_location_update, handle_group_kick, handle_group_leave, handle_group_leader, handle_send_group_chat
from talent import handle_respec_talent_tree, handle_allocate_talent_tree_points, handle_talent_claim, handle_talent_speedup, handle_train_talent_point, handle_clear_talent_research, handle_active_talent_change_request




# Pet Related Packets
#===================================
const_1262 = 0xF0 # PKTTYPE_PET_HATCH_OR_TRAIN
const_1134 = 0x37 # PKTTYPE_RECEIVE_NEW_PET
const_849 = 0xe4 # PKTTYPE_REQUEST_EGG_UPDATE
const_1081 = 0xef # PKTTYPE_PET_TRAINING_COMPLETE
const_1036 = 0xed  # PKTTYPE_CANCEL_PET_TRAINING - Cancels the pet training process
const_981 = 0xE5 # PKTTYPE_EGG_PET_UPDATE
const_1104 = 0xf2  # PKTTYPE_PET_EXPERIENCE_UPDATE
const_877 = 0xe8  # PKTTYPE_EGG_HATCH_CANCEL - Sent by the client to cancel an egg hatching process
const_939 = 0xe7  # PKTTYPE_EGG_HATCH_START - Sent by the server to notify the client that a new pet egg has started hatching
const_1114 = 0xec  # PKTTYPE_PET_TRAIN_START - Sent by the client to start training a pet
const_947 = 0xe6  # PKTTYPE_BARN_HATCH_OR_TRAIN - Client sends this when the player clicks to hatch a new egg or train a pet; payload includes egg ID/type for hatching, boolean flag for action type.
const_1190 = 0xE9  # PKTTYPE_PET_EGG_SPEEDUP - Client requests to accelerate egg hatching using Mammoth Idols (consumes idols based on remaining hatch time).
const_962 = 0xee  # PKTTYPE_PET_TRAINING_COMPLETE - Notifies the client that a pet has finished training; triggers a notification and updates pet training status.
const_709 = 0xb2  # PKTTYPE_MOUNT_EQUIP - Notifies the client to equip a specific mount for a given entity, or sent by the client to equip a mount for the player.
const_1209 = 0xb3  # PKTTYPE_PET_INFO_UPDATE - Sent by the client to update the server with the current active pet and resting pets, including their type IDs and unique instance IDs.
const_978 = 0xea  # PKTTYPE_PET_TRAINING_COMPLETE - Sent by the client to notify the server that the player's pet training or egg incubation has finished and the results should be applied.
const_1001 = 0xff  # PKTTYPE_NEW_HATCHERY_EGGS - Server notifies the client that new eggs are ready in the Hatchery
#===================================

# Inventory and Currency Related Packets
#===================================
const_1266 = 0x104 # PKTTYPE_UPDATE_LOCKBOX_INVENTORY
const_1023 = 0x10f # PKTTYPE_SPEND_ROYAL_SIGILS
const_1201 = 0x10c  # updates players consumables inventory when a  consumable is used
const_1028 = 0xb5  # updates players MammothIdols
const_1157 = 0xA1 # PKTTYPE_PREMIUM_CURRENCY_UPDATE
const_1219 = 0x106  # PKTTYPE_BUY_ROYAL_SIGIL_STORE
const_1115 = 0x105  # PKTTYPE_BUY_LOCKBOX_KEYS - Client requests to buy Lockbox/Dragon keys
const_1235 = 0xb4  # PKTTYPE_MONEY_LOSS - Server notifies client that the player lost gold
const_1303 = 0x10b  # PKTTYPE_CONSUMABLE_GAIN - Server notifies the client that the player has obtained consumable items; includes item ID, stack count, and whether to suppress pickup notification.
const_898 = 0x112  # PKTTYPE_ROYAL_SIGIL_REWARD - Server grants the player Royal Sigils (lockbox currency); updates total and caches amount earned.
const_1164 = 0x114  # PKTTYPE_LOCKBOX_OPEN - Client request sent to server when the player attempts to open a lockbox; includes lockbox ID and selected option index.
const_1289 = 0x107  # PKTTYPE_OPEN_LOCKBOX - Sent by the client to notify the server that the player is opening a lockbox, consuming one lockbox and one key. The server then processes rewards and updates the player's inventory accordingly.
const_884 = 0x108  # PKTTYPE_LOCKBOX_CONTENT - Sent by the server to the client to provide information about a specific lockbox's contents. Includes the lockbox type, item IDs, and optionally a custom name or description. The client then updates the lockbox UI accordingly.
PKTTYPE_RECEIVE_GOLD = 0x35
PKTTYPE_RECEIVE_GEAR = 0x33
PKTTYPE_RECEIVE_LOOTDROP = 0x32
PKTTYPE_RECEIVE_REWARD = 0x2b
const_1010 = 0x34  # PKTTYPE_MATERIAL_PICKUP - Server notifies the client that the player has acquired materials; client updates inventory and optionally shows a notification.
const_956 = 0x36  # PKTTYPE_GAIN_MOUNT - Server notifies client that the player has obtained a new mount; includes mount ID and a flag for whether to suppress notification.
const_1182 = 0x109  # PKTTYPE_GAIN_CHARM - Server notifies the client that the player gained a charm or respec stone; payload includes encoded charm ID and quantity/flags.
#===================================

# Combat and Health Related Packets
#===================================
const_1271 = 0x3b # PKTTYPE_ENTITY_HEAL
const_1142 = 0xf7 # PKTTYPE_RECALC_HEALTH
const_969 = 0xfc # PKTTYPE_SEND_COMBAT_STATS
const_1037 = 0xF9 # PKTTYPE_REQUEST_CLIENT_HP
const_1099 = 0xF6 # PKTTYPE_CLIENT_HP_REPORT
const_958 = 0x100  # PKTTYPE_CHAR_REGEN - Server packet sent when a character regenerates health; includes entity ID and amount of HP restored.
const_252 = 0x10d  # PKTTYPE_QUEUE_POTION - Notifies the client that a potion/consumable has been queued for use by a specific entity; triggers updating the next active potion.
const_909 = 0x10e # PKTTYPE_QUEUE_POTION
const_1255 = 0xfb  # PKTTYPE_SYNC_PLAYER_STATS - Server requests the client to resend its current melee, magic, and max HP stats; used to synchronize player stats between client and server.
PKTTYPE_SERVER_ADJUST_HP = 0x3a
PKTTYPE_ENT_DESTROY = 0x0d
PKTTYPE_BUFF_TICK_DOT = 0x79
PKTTYPE_REQUEST_RESPAWN = 0x77
PKTTYPE_ENT_POWER_HIT = 0xa
PKTTYPE_PROJECTILE_EXPLODE = 0xe
PKTTYPE_ENT_ADD_BUFF = 0xb
PKTTYPE_ENT_REMOVE_BUFF = 0xc
PKTTYPE_RESPAWN_COMPLETE = 0x80
PKTTYPE_CHAR_REGEN = 0x78
const_743 = 0x82  # PKTTYPE_REVIVE - Sent by the server to the client to indicate that a player/entity has been revived
const_760 = 0x8a # PKTTYPE_UPDATE_SPEED - Sent by the server to update an entity's movement speed
const_1127 = 0xbb  # PKTTYPE_REPORT_MAX_HP_CHANGE - Client informs the server that the player's maximum HP has changed, so the server can adjust stats or apply over-heal corrections
const_1300 = 0xcb  # PKTTYPE_POWER_USE_START - Sent by the client to the server when a player begins using a power that consumes mana
const_1239 = 0xcc  # PKTTYPE_HOTBAR_ABILITY_SWITCH - Client notifies the server that the player switched active abilities; payload is empty, server infers new state from current hotbar.
PKTTYPE_GRANT_REWARD = 0x2a
#===================================

# Room and Zone Related Packets
#===================================
const_805 = 0xAC # PKTTYPE_ROOM_BOSS_INFO
const_683 = 0xA5 # PKTTYPE_ROOM_EVENT_START
const_648 = 0xA9 # PKTTYPE_ROOM_STATE_UPDATE
const_762 = 0xa6  # PKTTYPE_ROOM_CLOSE / ROOM_RESET
const_823 = 0xad  # PKTTYPE_ROOM_UNLOCK - Notifies client that a room is now unlocked or accessible
const_788 = 0xAB  # PKTTYPE_ROOM_INFO_UPDATE - Updates room state: player count, room name, capacity, and owner name.
const_996 = 0xf4  # PKTTYPE_ZONE_ENTER - Client notifies server that the player has entered a new zone/room
const_1158 = 0xDA # PKTTYPE_ROOM_SCAFFOLDING_UPDATE
const_694 = 0xC2 # PKTTYPE_FLAMETHROWER_ROR_TRIGGER
const_1256 = 0x96  # PKTTYPE_ZONE_PLAYERS_UPDATE - Server sends the client the list of players currently in the same zone/area; client updates the Zone panel with this information.
const_1302 = 0x95  # PKTTYPE_ZONE_PANEL_REQUEST - Client requests the current players in the same zone/area
#===================================

# Entity Update Related Packets
#===================================
const_928 = 0xF1 # PKTTYPE_PLAYER_EQUIPMENT_UPDATE
const_1061 = 0xaf  # PKTTYPE_ENT_GEAR_UPDATE - Updates an entity's equipped gear (armor, weapons, accessories) on the client
const_1126 = 0x88  # PKTTYPE_SET_ENTITY_LEVELS - Server notifies the client of the new level for entities; client updates maxHP and related stats for all entities accordingly.
const_691 = 0xae  # PKTTYPE_SET_UNTARGETABLE
PKTTYPE_CHANGE_OFFSET_Y = 0x7d
PKTTYPE_ENT_INCREMENTAL_UPDATE = 0x7
const_1090 = 0xa2 # PKTTYPE_CLIENT_SYNC - Sent by the client to the server to synchronize the player's position, movement state, and tick timing
PKTTYPE_ENT_POWER_CAST = 0x9
PKTTYPE_ENT_FULL_UPDATE = 0x8
PKTTYPE_NEWLY_RELEVANT_ENTITY = 0xf
const_1152 = 0x8e # PKTTYPE_WRITE_CHANGE_LOOK - when the user changes his looks at the mirror
const_1175 = 0xba # PKTTYPE_APPLY_DYE - when the user dyes his gear or shirt/pants
const_941 = 0x8f # PKTTYPE_SEND_UPDATED_LOOK needs to be send by the server to update the players visuals  when PKTTYPE_WRITE_CHANGE_LOOK is received by the server
const_1041 = 0x111 # PKTTYPE_UPDATE_DYE - Sent by the server to the client to update an entity's equipped gear and shirt/pants
#===================================

# Mission and Level Related Packets
#===================================
const_990 = 0x86  # PKTTYPE_COMPLETE_MISSION - Marks a mission as complete
const_1031 = 0x89 # PKTTYPE_UPDATE_BONUS_LEVELS
PKTTYPE_MISSION_ADDED = 0x85
PKTTYPE_MISSION_COMPLETE = 0x84
PKTTYPE_LEVEL_STATE = 0x40
PKTTYPE_SET_LEVEL_COMPLETE = 0x3f
PKTTYPE_MISSION_PROGRESS = 0x83
PKTTYPE_CHANGE_LEVEL = 0x39
PKTTYPE_RECV_LEVEL_COMPLETE = 0x87
const_791 = 0xB7 # PKTTYPE_QUEST_PROGRESS_UPDATE
#===================================

# Emote and Sound Related Packets
#===================================
const_808 = 0xA7 # PKTTYPE_EMOTE
const_716 = 0xa8  # PKTTYPE_PLAY_SOUND - Plays a sound in the client's current room
PKTTYPE_EMOTE_BEGIN = 0x7e
PKTTYPE_EMOTE_END = 0x7f
#===================================

# Player Interaction Related Packets
#===================================
const_1197 = 0xF3 # PKTTYPE_REQUEST_VISIT_PLAYER_HOUSE
const_1020 = 0x6A # PKTTYPE_REQUEST_JOIN_PARTY
const_1161 = 0x8D # PKTTYPE_BADGE_INTERACT
const_1211 = 0x10A # PKTTYPE_DYE_UNLOCK
const_874 = 0x8b  # PKTTYPE_SEND_MAP_POSITION
const_617 = 0xaa  # PKTTYPE_ACTION_UPDATE - Server notifies client of a player action/input (jump, fire, drop, etc.) in a room
const_1171 = 0xa3  # PKTTYPE_ACTIVE_FIRE_HEARTBEAT - Sent periodically while player is firing/using abilities
const_1014 = 0xbc  # PKTTYPE_SAVE_KEYBINDS - Client sends updated keybinding configuration to the server; payload includes whether defaults are used and all custom keybind mappings.
const_905 = 0x3C # PKTTYPE_START_SKIT
const_1065 = 0x7b  # PKTTYPE_INTERACT_SKIT - Server tells the client that an entity should start a skit/dialogue; payload contains entity ID and optional skit ID to play.
PKTTYPE_TALK_TO_NPC = 0x7a
PKTTYPE_QUERYMESSAGE_QUESTION = 0x58
PKTTYPE_QUERYMESSAGE_ANSWER = 0x59
PKTTYPE_QUERYMESSAGE_INTERPRET = 0x5a
PKTTYPE_PICKUP_LOOTDROP = 0x38
#===================================

# Gear and Equipment Related Packets
#===================================
const_1280 = 0xF5 # PKTTYPE_LEVEL_GEAR_LIST - populates the Armory with the Gear that the player owns
const_773 = 0xb0  # PKTTYPE_EQUIP_RUNNES Send by the client when runnes are added to a weapon
const_1029 = 0x31 # PKTTYPE_EQUIP_GEAR - send by the client
PKTTYPE_UPDATE_EQUIPMENT = 0x30
#===================================

# Talent and Skill Related Packets
#===================================
const_1089 = 0xd2 # PKTTYPE_RESPEC_TALENT_TREE
const_987 = 0xD6  # Client → Server: Claim a completed Master Class Tower research point (grants a new talent point)
const_1284 = 0xE0  # Client → Server: Spend Mammoth Idols to speed up Master Class Tower talent research
const_1044 = 0xD4  # Client → Server: Begin training a new Master Class Tower talent point (includes class index + free/paid flag)
const_1220 = 0xDF  # Client → Server: Cancel/clear current Master Class Tower research in progress
const_1047 = 0xD3  # Client → Server: Update Forge upgrade points
const_920 = 0xD5  # Server → Client: Notify that Master Class Tower research has completed (talent point ready to claim)
const_929 = 0xBD  # Client → Server: Update hotbar skill assignments (which abilities are equipped in each slot)
const_1077 = 0xBE  # Client → Server: Begin training a new skill rank in the Ability Book/Tome (abilityID, newRank, free/paid flag)
const_1205 = 0xD1  # Client → Server: Claim a completed Ability Book/Tome skill research (grants new rank in learnedAbilities)
const_1129 = 0xDD # Client → Server : Cancel the current ongoing skill research
const_1111 = 0xde # Client → Server : Speed up the current Skill Research
const_966 = 0xbf  # Server → Client : tells the client that the skills research has completed and is ready to claim
const_1133 = 0xc0 # Client → server : tells the server the player has allocated new points in the talent tree
#===================================

# Forge Related Packets
#===================================
const_889 = 0xe2
const_1273 = 0xd0
const_937 = 0xb1
const_1192 = 0xe1
const_789 = 0x110
const_1153 = 0xcd
const_1105 = 0xcf  # PKTTYPE_MAGIC_FORGE_REROLL - Client requests the server to reroll the currently crafting Magic Forge item
#===================================

# Gear Set Related Packets
#===================================
const_976 = 0xc8 # Client → server : tells the server if a gearset has been renamed
const_843 = 0xc7 # Client → server : tells the server when a new gearset is created
const_893 = 0xc6 # Client → server : tells the server when the player has equipped a gearset
#===================================

# Buildings Upgrade Packets
#===================================
const_1032 = 0xdb # Client → server : cancel the current ongoing upgrading building
const_1187 = 0xdc # Client → server : Building upgrade speed up request
const_861 = 0xd7 # Client → server : client notifies the server when the player has started an upgrade
const_838 = 0xd8 # Server → Client : server notifies the client when a building has finished upgrading
const_1027 = 0xe3 # Server → Client : the actual purpose of this packet is unknown what it does is  if the client receives this packet the client will refresh the home buildings like Forge,Tome,etc..
const_878 = 0xd9 # Client → server : client acknowledged a completed building upgrade it gets sent after 0xD8 completion has been processed

#===================================

# Master Class Related Packets
#===================================
const_767 = 0xc3
const_1137 = 0xc1
#===================================

# Login Screen Related Packets
#===================================
PKTTYPE_LOGIN_VERSION = 0x11
PKTTYPE_LOGIN_CHALLENGE = 0x12
PKTTYPE_LOGIN_CREATE = 0x13
PKTTYPE_LOGIN_CHARACTER_LIST = 0x15
PKTTYPE_LOGIN_AUTHENTICATE = 0x14
PKTTYPE_LOGIN_CHARACTER_SELECT = 0x16
PKTTYPE_LOGIN_CHARACTER_CREATE = 0x17
PKTTYPE_LOGIN_FAILURE = 0x1b
const_1263 = 0x1a
const_840 = 0x19
const_897 = 0xb6  # PKTTYPE_MAX_CHARACTERS - Server tells client the maximum number of characters (login slots) the account is allowed.
#===================================

# Enter Game World / Level Transfer Related Packets
#===================================
const_945 = 0x21
PKTTYPE_WELCOME = 0x10
PKTTYPE_GAMESERVER_LOGIN = 0x1f
PKTTYPE_TRANSFER_READY = 0x1d
PKTTYPE_OPEN_DOOR = 0x2d
PKTTYPE_DOOR_TARGET = 0x2e
PKTTYPE_REQUEST_DOOR_STATE = 0x41
PKTTYPE_DOOR_STATE = 0x42
#===================================

# Standalone and Developer Mode Related Packets
#===================================
PKTTYPE_GAME_TO_MASTER_END_LEVEL = 0x25
PKTTYPE_MASTER_CLIENT = 0x1e
PKTTYPE_GAME_TO_MASTER_START_LEVEL = 0x24
PKTTYPE_GAME_TO_MASTER_PORT = 0x23
#===================================

# Social Related Packets
#===================================
PKTTYPE_FRIEND_REMOVED = 0x93
PKTTYPE_CHAT_MESSAGE = 0x2c
PKTTYPE_ROOM_THOUGHT = 0x76
PKTTYPE_RECV_CHAT_PRIVATE = 0x47
PKTTYPE_CHAT_STATUS = 0x44 # Gray chat text
PKTTYPE_SEND_CHAT_OFFICER = 0x61
PKTTYPE_SEND_CHAT_PRIVATE = 0x46
PKTTYPE_RECV_CHAT_OFFICER = 0x62
const_1141 = 0x3d # Gray chat text
const_985 = 0x102 # Admin chat Announcement # yellow color
const_839 = 0x81  # PKTTYPE_STATUS_TEXT_UNSAFE - Server sends a raw/unfiltered status message to the client (possibly containing unsafe or special formatting); displayed directly in the chat window.
const_1183 = 0x48  # PKTTYPE_SEND_WHISPER - Server notifies client of a private message (whisper) from another player
const_616 = 0x90 # PKTTYPES_SEND_FRIEND_REQUEST
const_610 = 0x91 # PKTTYPES_UNFRIEND - client sends request to remove player from the friend list
const_913 = 0xc9 # PKTTYPE_REQUEST_FRIEND_LIST
const_1178 = 0xca  # PKTTYPE_FRIENDLIST_UPDATE - Server sends the full friend list and updates friend statuses
const_1298 = 0x92  # PKTTYPE_FRIEND_UPDATE - Sent by the server when a friend’s status changes (online/offline, friend request, accepted, etc.)
const_901 = 0x98 # PKTTYPE_FRIEND_LOGGED_OFF
const_1039 = 0x43 # PKTTYPE_CHAT_IGNORE - sends a request to the server to ignore a player
const_1165 = 0x9d  # PKTTYPE_PLAYER_IGNORE_RECEIVE - received by the server when the player has been ignored
const_1052 = 0x9e  # PKTTYPE_IGNORE_LIST_REQUEST - Sent by the client to request the current list of ignored players from the server
const_1241 = 0x9f  # PKTTYPE_IGNORE_LIST_UPDATE - Server sends the client the current list of ignored players, which the client then displays in the ignore panel.
const_1229 = 0x9c  # PKTTYPE_IGNORE_REMOVE - Server confirms a player has been removed from your ignore list
const_451 = 0xc5
#===================================

# Guild Related Packets
#===================================
PKTTYPE_CMD_GUILD_DEMOTE = 0x52
PKTTYPE_CMD_GUILD_QUIT = 0x54
PKTTYPE_GUILD_UPDATE = 0x56
PKTTYPE_RECV_CHAT_GUILD = 0x60
PKTTYPE_CMD_GUILD_LEADER = 0x53
PKTTYPE_CMD_GUILD_DISBAND = 0x4e
PKTTYPE_CMD_GUILD_INVITE = 0x4f
PKTTYPE_CMD_GUILD_KICK = 0x50
PKTTYPE_CLEAR_GUILDCACHE = 0x55
PKTTYPE_CMD_GUILD_CREATE = 0x4d
PKTTYPE_GUILD_REFRESH_MEMBERSHIP = 0x57
PKTTYPE_CMD_GUILD_PROMOTE = 0x51
PKTTYPE_SEND_CHAT_GUILD = 0x5f
PKTTYPE_ONLINE_USER_GUILD_STATUS = 0x5d
const_1008 = 0x9a  # PKTTYPE_GUILD_MEMBER_JOINED - Server notifies the client that a new player has joined the guild; client updates the guild member list and shows a chat notification.
const_1260 = 0x99  # PKTTYPE_GUILD_RANK_CHANGE - Notifies the client of a guild member's promotion, demotion, or leadership change; updates rank display and chat notifications.
const_1112 = 0x9b  # PKTTYPE_GUILD_MEMBER_LEFT - Notifies the client when a guild member leaves or is kicked
const_879 = 0x97  # PKTTYPE_GUILD_MEMBER_ONLINE - Sent by the server when a guild member logs in to notify the client
#===================================

# Party Related Packets
#===================================
PKTTYPE_CMD_GROUP_INVITE = 0x65
PKTTYPE_GROUP_UPDATE = 0x75
PKTTYPE_TOLOGIN_GROUP_INVITE = 0x6c
PKTTYPE_SEND_CHAT_GROUP = 0x63
PKTTYPE_CMD_GROUP_LEADER = 0x68
PKTTYPE_TOLOGIN_GROUP_REMOVE = 0x6e
PKTTYPE_CMD_GROUP_KICK = 0x67
PKTTYPE_TOLOGIN_GROUP_LEADER = 0x6f
PKTTYPE_TOLOGIN_GROUP_ADD = 0x6d
PKTTYPE_CMD_GROUP_LEAVE = 0x66
PKTTYPE_RECV_CHAT_GROUP = 0x64
const_876 = 0x8c  # PKTTYPE_PARTY_UPDATE (likely)
const_1276 = 0x6b # PKTTYPE_TELEPORT_TO_PLAYER
#===================================

# Miscellaneous Packets
#===================================
const_894 = 0x3e  # PKTTYPE_TRADE_MODE_ENABLE - Server notifies the client that transfer/trade mode has been enabled
PKTTYPE_CLIENT_ERROR = 0x7c # client crash Reports
const_975 = 0xfa # PKTTYPE_UPDATE_CYCLE
const_924 = 0xA4 # PKTTYPE_HEARTBEAT
const_707 = 0x69 # PKTTYPE_LOCK/UNLOCK Command
const_1295 = 0x103  # PKTTYPE_NEWS_UPDATE
const_1214 = 0x101  # PKTTYPE_SERVER_MAINT_WARNING
const_1208 = 0xC4 # PKTTYPE_SESSION_STATS
const_1272 = 0x113 # Alert State update
const_900 = 0xf8 # PKTTYPE_UPDATE_COMBAT_STATS - Sent by the client to the server to update the entity's current combat stats, including health, gear bonuses, and magic-related calculations.
#===================================

# Unused or Legacy Packets
#===================================
PKTTYPE_TRANSFER_BEGIN = 0x1c
PKTTYPE_GAME_TO_LOGIN_USER_TRANSFER = 0x2f
PKTTYPE_GAME_TO_LOGIN_READY = 0x26
PKTTYPE_RELAY_TO_CHARNAME = 0x4a
PKTTYPE_RELAY_PACKET_SENDTOCLIENT = 0x4c
PKTTYPE_RELAY_TO_CHARID = 0x49
PKTTYPE_GAME_TO_LOGIN_USER_LEFT = 0x28
PKTTYPE_GAME_TO_LOGIN_USER_JOINED = 0x27
PKTTYPE_RELAY_PACKET_PROCESS = 0x4b
PKTTYPE_LOGIN_TO_GAME_NOTIFY_OFFLINE = 0x5c
PKTTYPE_LOGIN_TO_GAME_NOTIFY_ONLINE = 0x5b
PKTTYPE_LOGIN_TO_GAME_LOAD_LEVEL = 0x20
PKTTYPE_LOGIN_TO_GAME_KICK_USER = 0x45
PKTTYPE_GAME_TO_LOGIN_MAP_CLOSED = 0x29
const_1397 = 0x70
const_1395 = 0xfe
const_1377 = 0x5e
const_1321 = 0x22
const_1378 = 0xfd
const_1329 = 0x72
const_1306 = 0x74
const_1347 = 0x73
const_1348 = 0xa0
const_1368 = 0x94
const_1369 = 0xeb
const_1353 = 0xb8
const_1337 = 0x71
const_1358 = 0xb9
const_1415 = 0xce
const_933 = 0x18
#===================================

def ignore(session, data):
    return

PACKET_HANDLERS = {

    # Login.py
    ############################################
    0x11:   handle_login_version,
    0x13:   handle_login_create,
    0x14:   handle_login_authenticate,
    0x17:   handle_login_character_create,
    0x16:   handle_character_select,
    0x1f:   handle_gameserver_login, # Welcome / Player_Data (finalize level transfer and spawn NPCs)
    ############################################

    # dev.py
    ############################################
    0x1E:   DEVFLAG_MASTER_CLIENT,
    0xB7:   handle_quest_progress_update,
    0x40:   handle_level_state,
    0xa8:   handle_play_sound,
    0xaa:   handle_action_update,
    0xA7:   handle_emote,
    0xA9:   handle_room_state_update,
    0xA5:   handle_room_event_start,
    0xAB:   handle_room_info_update,
    0xae:   handle_set_untargetable,
    0xa6:   handle_room_close,
    0xad:   handle_room_unlock,
    0xAC:   handle_room_boss_info,
    0x7f:   handle_emote_end,
    ############################################

    # level_config.py
    ############################################
    0x2D:   handle_open_door,
    0x1D:   handle_level_transfer_request, # Transfer Ready (prepare ENTER_WORLD, do NOT finalize session.current_level)
    0x41:   handle_request_door_state,
    0x07:   handle_entity_incremental_update,
    ############################################

    # forge.py
    ############################################
    0xB1:   handle_start_forge,
    0xE2:   handle_forge_speed_up_packet,
    0xD0:   handle_collect_forge_charm,
    0xE1:   handle_cancel_forge,
    0x110:  handle_use_forge_xp_consumable,
    0xD3:   handle_allocate_magic_forge_artisan_skill_points,
    0xCF:   handle_magic_forge_reroll,
    ############################################

    # talent.py
    ############################################
    0xD2:   handle_respec_talent_tree,
    0xC0:   handle_allocate_talent_tree_points,
    0xD6:   handle_talent_claim,
    0xE0:   handle_talent_speedup,
    0xD4:   handle_train_talent_point,
    0xDF:   handle_clear_talent_research,
    0xC3:   handle_active_talent_change_request,
    ############################################

    # skills.py
    ############################################
    0xD1:   handle_skill_trained_claim,
    0xDD:   handle_skill_research_cancel_request,
    0xDE:   handle_skill_speed_up_request,
    0xBE:   handle_start_skill_training,
    0xBD:   handle_equip_active_skills,
    ############################################

    # entity.py
    ############################################
    0x08:   handle_entity_full_update,
    ############################################

    # combat.py
    ############################################
    0x0D:   handle_entity_destroy,
    0x79:   handle_buff_tick_dot,
    0x82:   handle_respawn_broadcast,
    0x77:   handle_request_respawn,
    0x0A:   handle_power_hit,
    0x0E:   handle_projectile_explode,
    0x0B:   handle_add_buff,
    0x0C:   handle_remove_buff,
    0x8A:   handle_change_max_speed,
    0x09:   handle_power_cast,
    0x7D:   handle_change_offset_y,
    0x78:   handle_char_regen,
    0x100:  handle_char_regen_tick,  # this one seems to be used only when "DEVFLAG_STANDALONE_CLIENT" has been enabled
    0xB0:   handle_equip_rune,
    0x31:   handle_update_single_gear,
    0x30:   handle_update_equipment,
    0xC7:   handle_create_gearset,
    0xC8:   handle_name_gearset,
    0xC6:   handle_update_gearset,
    ############################################

    # buildings.py
    ############################################
    0xD7:   handle_building_upgrade,
    0xDC:   handle_building_speed_up_request,
    0xDB:   handle_cancel_building_upgrade,
    0xD9:   handle_building_claim,
    ############################################

    # socials.py
    ############################################
    0x95:   handle_zone_panel_request,
    0x2C:   handle_public_chat,
    0x46:   handle_private_message,
    0x76:   handle_room_thought,
    0xC5:   handle_start_skit,
    0x7E:   handle_emote_begin,
    0x65:   handle_group_invite,
    0x59:   handle_query_message_answer,
    0x8b:   handle_map_location_update,
    0x67:   handle_group_kick,
    0x66:   handle_group_leave,
    0x68:   handle_group_leader,
    0x63:   handle_send_group_chat,
    ############################################

    # pets.py
    ############################################
    0xB3:   handle_equip_pets,
    0xB2:   handle_mount_equip_packet,
    0xE4:   handle_request_hatchery_eggs,
    0xEC:   handle_train_pet,
    0xEF:   handle_pet_training_collect,
    0xED:   handle_pet_training_cancel,
    0xF0:   handle_pet_speed_up,
    0xE6:   handle_egg_hatch,
    0xE9:   handle_egg_speed_up,
    0xEA:   handle_collect_hatched_egg,
    0xE8:   handle_cancel_egg_hatch,
    ############################################

    # Character.py
    ############################################
    0xF4:   handle_request_armory_gears,
    0x113:  handle_alert_state_update,
    0x19:   PaperDoll_Request,
    ############################################

    # globals.py
    ############################################
    0x7C:   Client_Crash_Reports,
    ############################################

    # commands.py
    ############################################
    0x8D:   handle_badge_request,
    0xA2:   handle_linkupdater,
    0x7A:   handle_talk_to_npc,
    0x8E:   handle_change_look,
    0xBA:   handle_apply_dyes,
    0x107:  handle_lockbox_reward,
    0x10E:  handle_queue_potion,
    0xBB:   handle_hp_increase_notice,
    0x2A:   handle_grant_reward,
    0xCB:   handle_power_use,
    0x38:   handle_pickup_lootdrop,
    0x3f:   handle_set_level_complete,
    0xfc :  handle_send_combat_stats,
    0xC4 :  handle_dungeon_run_report,
    ############################################

     # other
     ############################################
     0xCC: ignore # Client sends this when a new skill is equipped,actual hotbar update follows in 0xBD: handle_equip_active_skills.

}