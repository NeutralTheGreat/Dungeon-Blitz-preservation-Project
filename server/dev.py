import struct

from BitBuffer import BitBuffer
from bitreader import BitReader
from globals import GS
from login import handle_gameserver_login
"""
Some context : 

if "<DEVFLAG_STANDALONE_CLIENT />" is enabled in the "devSettings" 
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

def DEVFLAG_STANDALONE_CLIENT(session, data):
    br = BitReader(data[4:])
    value = br.read_method_9()
    boolean = br.read_method_15()

    print(f" value : {value} : Boolean {boolean}")

    for t, (char, _, _) in GS.pending_world.items():
        if session.user_id is None or char.get("user_id") == session.user_id:
            handle_gameserver_login(session, build_fake_login_packet(t))
            return
