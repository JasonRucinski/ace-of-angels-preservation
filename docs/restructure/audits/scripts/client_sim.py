"""Synthetic 'stable' image to exercise prepare_client composition without game files."""
import hashlib, sys, tempfile, json
from pathlib import Path
sys.path.insert(0, "/home/user/ace-of-angels-preservation/tools")
import prepare_client as pc, local_station, physics_timestep, archive_terminator, explicit_protection, online_terrain
import asteroid_render, station_detail, texture32, third_person, own_ship_model, own_ship_menu, frame_clock, visibility_fix
import menu_aspect, cursor_warp, powerup_pickup, object_persistence, world_detail, solid_world_render
buf = bytearray(0x210000)
def put(off, b): buf[off:off+len(b)] = b
for m in (cursor_warp, menu_aspect, own_ship_model, visibility_fix, object_persistence, frame_clock, powerup_pickup, asteroid_render, station_detail, texture32):
    for off, old, new in m.regions(): put(off, old)
for off, old, new in third_person.regions(): put(off, old)
for off, old, new in own_ship_menu.regions(): put(off, old)
for off, old, new in world_detail.regions(): put(off, old)
put(pc.BACKGROUND_OFFSET, pc.BACKGROUND_JNE)
put(local_station.OFFSET, local_station.ORIGINAL)
put(physics_timestep.SITE_OFFSET, physics_timestep.DISPLACED)
put(archive_terminator.SITE_OFFSET, archive_terminator.DISPLACED)
put(explicit_protection.SITE_OFFSET, explicit_protection.DISPLACED)
put(online_terrain.SITE_OFFSET, online_terrain.DISPLACED)
stable = bytes(buf)
h = hashlib.sha256(stable).hexdigest()
pc.STABLE_SHA256 = h; physics_timestep.STABLE_SHA256 = h; local_station.STABLE_SHA256 = h
print("synthetic stable inspect:", pc.inspect(stable))
d = Path(tempfile.mkdtemp(dir=sys.argv[1]))
exe = d / "AOACLIENT.EXE"; exe.write_bytes(stable)
r = pc.prepare(exe, chase_camera=False)
print("after launcher-style prepare chase off:", third_person.NAME in r["patches"])
# 1) plain CLI prepare (what play.md tells LAN users to run)
r = pc.prepare(exe, host="aoalan", experimental_protection=False)
print("after `prepare --station aoalan --no-experimental-protection`: chase on again =", third_person.NAME in r["patches"])
pc.prepare(exe, chase_camera=False)
# 2) asteroid_render.main flow
source = exe.read_bytes()
result = asteroid_render.configure(source, True)
pc.prepare(exe, host=pc.inspect(result)["host"], experimental_asteroids=True)
print("asteroid tool verification would", "PASS" if exe.read_bytes()==result else "FAIL (exe already rewritten, chase re-enabled=%s)" % (third_person.NAME in pc.inspect(exe.read_bytes())["patches"]))
# 3) third_person v1 reported as v3
v1 = bytearray(pc.configure(stable, chase_camera=False))
for off, old, new in third_person.regions("v1"): v1[off:off+len(old)] = new
print("v1 cave reported as:", [p for p in pc.inspect(bytes(v1))["patches"] if "third" in p])
# 4) shared constants: distant objects + solid world
both = pc.configure(stable, distant_objects=True, experimental_solids=True)
import struct
print("0x59D9C0 (solid-world/asteroid 900000 horizon) now =", struct.unpack_from("<f", both, 0x19D9C0)[0])
print("0x5B0C30 (asteroid 'ordinary' 61000 gate) now =", struct.unpack_from("<f", both, 0x1B0C30)[0])
# 5) launcher option set covers explicit protection?
prot = pc.configure(stable, experimental_protection=True)
try:
    pc.configure(prot, host="aoalan")
except ValueError as e: print("launcher station change with protection installed ->", e)
# 6) object_persistence.install with menu framing off
pc.prepare(exe, menu_framing=False)
orig_check = pc.check
pc.check = lambda e, require_assets=True: {**pc.inspect(Path(e).read_bytes()), "status": "ready"}
try:
    object_persistence.install(exe)
    print("object_persistence.install: ok")
except ValueError as e:
    print("object_persistence.install with menu framing off ->", e, "| menu framing now:", menu_aspect.NAME in pc.inspect(exe.read_bytes())["patches"])
# 7) texture32.install silently re-enables chase
pc.prepare(exe, chase_camera=False)
for p in d.glob("*.before-*"): p.unlink()
texture32.install(exe)
print("texture32.install re-enabled chase:", third_person.NAME in pc.inspect(exe.read_bytes())["patches"])
# 8) launcher on an undone client
import client_launcher
pc.check = orig_check
pc.check_assets = lambda folder: 0
pc.prepare(exe, undo=True)
pc.PRISTINE = None
try:
    opts, avail = client_launcher.read_settings(d)
    print("launcher read_settings on undone client: accepted, station shown =", opts["station"])
except Exception as e:
    print("launcher refused undone client:", e)
