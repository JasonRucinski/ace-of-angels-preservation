import sys
sys.path.insert(0, "/home/user/ace-of-angels-preservation/tools")
import patch_client, physics_timestep, archive_terminator, explicit_protection, cursor_warp, menu_aspect
import third_person, own_ship_model, own_ship_menu, visibility_fix, object_persistence, frame_clock
import powerup_pickup, asteroid_render, solid_world_render, station_detail, world_detail, texture32, online_terrain
import render_clock_experiment, render_culling_experiment, prepare_client, local_station
from patch_client import jmp_patch
B=0x400000
R=[]
def add(name, off, n): R.append((name, off+B, off+B+n))
# patch_client
cave, labels = patch_client.build_cave()
add("logger(patch_client) cave", patch_client.CAVE-B, len(cave))
for va,n in ((0x551775,2),(0x526D00,8),(0x526F8C,11),(0x527210,8),(0x527233,9)): add("logger(patch_client) site", va-B, n)
add("logger lock words(.data)", patch_client.LOCK_OWNER-B, 8)
code = physics_timestep.guard_code(); add("physics cave", physics_timestep.CAVE_OFFSET, len(code)); add("physics site", physics_timestep.SITE_OFFSET, 6)
add("hostname field", local_station.OFFSET, 12)
add("background jne", prepare_client.BACKGROUND_OFFSET, 2)
c=archive_terminator.cave_code(); add("archive_terminator cave", archive_terminator.CAVE_OFFSET, len(c)); add("archive_terminator site", archive_terminator.SITE_OFFSET, len(archive_terminator.DISPLACED))
c=explicit_protection.cave_code(); add("explicit_protection cave", explicit_protection.CAVE_OFFSET, len(c)); add("explicit_protection site", explicit_protection.SITE_OFFSET, len(explicit_protection.DISPLACED))
for name, mod in (("cursor_warp",cursor_warp),("menu_aspect",menu_aspect),("own_ship_model",own_ship_model),("own_ship_menu",own_ship_menu),("visibility_fix",visibility_fix),("object_persistence",object_persistence),("frame_clock",frame_clock),("powerup_pickup",powerup_pickup),("asteroid_render",asteroid_render),("station_detail",station_detail),("texture32",texture32),("render_clock_experiment",render_clock_experiment),("render_culling_experiment",render_culling_experiment)):
    for off, old, new in mod.regions(): add(name, off, len(old))
for v in ("v3","v2","v1"):
    for off, old, new in third_person.regions(v): add("third_person "+v, off, len(old))
for off, old, new in own_ship_menu.regions(True): add("own_ship_menu legacy", off, len(old))
for off, old, new in solid_world_render.regions(): add("solid_world_render", off, len(old))
for off, old, new in world_detail.regions(): add("world_detail", off, len(old))
add("online_terrain cave(REGION)", online_terrain.CAVE_OFFSET, online_terrain.REGION); add("online_terrain site", online_terrain.SITE_OFFSET, 5)
# data tail for third_person
add("third_person .data FAKE..ARMED", third_person.FAKE-B, third_person.ARMED+1-third_person.FAKE)
add("own_ship_menu RESTRICT(.data)", own_ship_menu.RESTRICT-B, 1)
R.sort(key=lambda r:r[1])
for n,a,b in R: print(f"{a:#09x}-{b:#09x} ({b-a:4d}) {n}")
print("--- overlaps (different module families) ---")
fam=lambda n:n.split()[0].split("(")[0]
for i,(n1,a1,b1) in enumerate(R):
    for n2,a2,b2 in R[i+1:]:
        if a2<b1 and fam(n1)!=fam(n2):
            print(f"{n1} [{a1:#x},{b1:#x}) x {n2} [{a2:#x},{b2:#x})")
