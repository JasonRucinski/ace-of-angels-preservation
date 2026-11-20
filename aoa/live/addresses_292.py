"""Addresses in the running 2.9.2 client (image base 0x400000) that the live tools read.

One copy for aoa/live/arena.py, aoa/live/frame_pacing.py and
aoa/reel/client_mem.py; aoa/live/procmem.py checks the build first through
PE_TIMESTAMP. Offsets were recovered from AllocNewPlayer, LoadPlayer,
ReceivePositionUpdate and the main loop (see each user for the code site).
"""
IMAGE_BASE = 0x400000
# TimeDateStamp of the 2.9.2 client's PE header, 2003-09-26T04:47:08Z
# (manifest/downloads.json, client_pe_timestamp_utc).
PE_TIMESTAMP = 0x3F73C4CC

WORLD = 0x5E7728            # pointer to the world object
PLAYERS = 0xD32AC           # player slot array inside the world
PLAYER_STRIDE = 0x3B0       # bytes per player slot
GAME_CLOCK = 0x5E8E5C       # game clock, set by 0x529700 / 0x5296C0
APP_POINTER = 0x5E6E58      # application object; +FRAME_COUNTER counts presents
FRAME_COUNTER = 0x38        # `inc` at 0x44AF94, just before each present
APP_ACTIVE = 0x5E6E28       # main loop renders only while set (0x408061)
GRAPHICS_POINTER = 0x60C828  # graphics object
MAIN_CAMERA = 0x2510        # main camera matrix inside graphics, copied by 0x553810
JOYSTICK_AXES = 0x60CC14
