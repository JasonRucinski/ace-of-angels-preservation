"""Render recovered map exports into a local HTML gallery; no game is launched.

Uses the original exported textures and heuristic scene2obj geometry. Artifacts
belong under ignored work/, not in a published or committed asset bundle.
"""
import argparse
import hashlib
import html
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = {
    "Arena1a": ("RingPan", "Ring structures close-up", "Ring structures, asteroids, docks and a distant base."),
    "CTF_arena": (None, None, "Asteroid layout with exported turret and flag geometry. Both base nodes are unresolved."),
    "CTF_arena_b": ("NewDock", "Dock close-up", "Asteroid layout with dock geometry; a separate CTF arena candidate."),
    "newterrain": ("RingPan", "Ring structures close-up", "Related ring-and-asteroid layout with additional exported ship geometry."),
    "outerchange": ("NewDock", "Dock close-up", "Very incomplete export: docks, flags and a distant base. Most nodes are unresolved."),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenes", type=Path, default=ROOT / "work/2.9.2/scenes")
    parser.add_argument("--out", type=Path, default=ROOT / "work/map-previews")
    parser.add_argument("--size", type=int, default=1000)
    args = parser.parse_args()
    if not 256 <= args.size <= 2048:
        parser.error("size must be 256..2048")
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    scenes = list(CANDIDATES) + [p.stem.removesuffix("_nodes") for p in sorted(args.scenes.glob("*_nodes.json"))
                                if p.stem.removesuffix("_nodes") not in CANDIDATES]
    for name in scenes:
        obj = args.scenes / (name + ".obj")
        nodes_path = args.scenes / (name + "_nodes.json")
        mtl = obj.with_suffix(".mtl")
        nodes = json.loads(nodes_path.read_text())
        textures = [args.scenes / line.split(None, 1)[1] for line in mtl.read_text().splitlines()
                    if line.startswith("map_Kd ")]
        missing = [str(p) for p in textures if not p.is_file()]
        if missing:
            raise ValueError(f"{name}: missing textures: {missing}")
        views = [("overview", "Full exported layout · oblique", 35, 25, None)]
        if name in CANDIDATES:
            views.append(("top", "Full exported layout · top", 0, 90, None))
            focus, title, description = CANDIDATES[name]
            if focus:
                views.append(("detail", title + " · cropped", 35, 25, focus))
            if name in ("Arena1a", "newterrain"):
                views.append(("rings", "Ring structures · top close-up · cropped", 0, 90, focus))
            if name == "outerchange":
                views.append(("base", "Distant base close-up · cropped", 35, 25, "Hy_Base"))
        else:
            description = "Recovered asteroid-field component." if name.startswith("ast_fld") else "Recovered base/component layout; not established as a standalone arena."
        images = []
        for suffix, title, yaw, pitch, focus in views:
            output = args.out / f"{name}-{suffix}.png"
            command = [sys.executable, "-I", str(ROOT / "tools/render_obj.py"), str(obj), str(output),
                       str(args.size), str(yaw), str(pitch)]
            if focus:
                command += ["--focus", focus]
            subprocess.run(command, check=True, timeout=120)
            data = output.read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
            assert struct.unpack_from(">II", data, 16) == (args.size, args.size)
            images.append({"file": output.name, "title": title, "yaw": yaw, "pitch": pitch,
                           "camera_focus_prefix": focus, "sha256": hashlib.sha256(data).hexdigest()})
        results.append({"name": name, "candidate": name in CANDIDATES, "description": description,
                        "nodes": len(nodes), "geometry_nodes": sum("model" in n for n in nodes),
                        "unresolved_nodes": [n["name"] for n in nodes if "model" not in n],
                        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in (obj, mtl, nodes_path)}, "images": images})
    manifest = {"scope": "Recovered exported geometry and original textures; heuristic object matching; no real-client loading/collision/scenario verification",
                "camera": "Orthographic; each view fitted independently, not a shared scale; close-ups may crop surrounding geometry",
                "lighting": "Preview renderer lighting; original game sky, effects and HUD are not reproduced",
                "maps": results}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    esc = html.escape
    sections = []
    for item in results:
        images = item["images"]
        primary = next((i for i in images if i["file"].endswith("-detail.png")), images[0])
        figures = "".join(f'<figure><a href="{esc(i["file"])}" target="_blank"><img loading="lazy" src="{esc(i["file"])}" alt="{esc(item["name"] + ": " + i["title"])}"></a><figcaption>{esc(i["title"])}</figcaption></figure>' for i in images)
        unresolved = " · ".join(item["unresolved_nodes"]) or "None in this export."
        sections.append(f'''<section id="{esc(item['name'])}" class="{'candidate' if item['candidate'] else 'component'}">
<div class="heading"><div><p class="eyebrow">{'ARENA CANDIDATE' if item['candidate'] else 'COMPONENT'}</p><h2>{esc(item['name'])}</h2></div>
<span>{item['geometry_nodes']} / {item['nodes']} nodes exported as geometry</span></div>
<p>{esc(item['description'])}</p>
<a href="{esc(primary['file'])}" target="_blank"><img class="hero" src="{esc(primary['file'])}" alt="{esc(item['name'] + ': ' + primary['title'])}" loading="lazy"></a>
<p class="caption">{esc(primary['title'])} — click to open full resolution</p>
<details><summary>All views ({len(images)})</summary><div class="views">{figures}</div></details>
<details><summary>Nodes not represented by geometry ({len(item['unresolved_nodes'])})</summary><p>{esc(unresolved)}</p></details></section>''')
    links = " ".join(f'<a href="#{esc(name)}">{esc(name)}</a>' for name in CANDIDATES)
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ace of Angels · recovered map previews</title><style>
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#11141b;color:#e7eaf0;font:16px/1.6 system-ui,sans-serif}
main{max-width:1120px;margin:auto;padding:48px 24px}h1{font-size:42px;line-height:1.1;max-width:750px;margin:12px 0 24px}h2{font-size:30px;margin:0}p{max-width:850px;color:#bac4d4}
.eyebrow{font-size:12px;letter-spacing:.16em;color:#9ac9ef;margin:0 0 8px}nav{display:flex;gap:12px;flex-wrap:wrap;margin:32px 0}a{color:#9ac9ef}nav a{background:#242b38;padding:8px 16px;border-radius:6px;text-decoration:none}
section{padding:40px 0;border-top:1px solid #343c4a;scroll-margin-top:24px}.heading{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}.heading span,.caption{font-size:14px;color:#a4afc1}
.hero{display:block;width:100%;max-width:780px;margin:24px auto 0}.caption{text-align:center;max-width:none}summary{cursor:pointer;padding:12px 0;color:#9ac9ef}details p{font-size:14px;overflow-wrap:anywhere}.views{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}figure{margin:0}figure img{width:100%}figcaption{font-size:14px;color:#bac4d4}.notice{background:#212836;padding:20px 24px;border-radius:8px}
</style><main><p class="eyebrow">ACE OF ANGELS / 2.9.2 / LOCAL ASSET REVIEW</p>
<h1>Explore the recovered maps</h1><p>Rendered from the actual exported meshes and textures. Five arena candidates first, followed by asteroid fields and base components.</p>
<div class="notice">These are reconstruction previews, not in-game screenshots. Missing nodes are not drawn; some are markers, others may be missing geometry. Full views preserve exported spacing, while labeled close-ups crop surrounding objects. Views use independent scales and simplified lighting. No collision or scenario behavior is implied.</div>
<nav>''' + links + '</nav>' + "\n".join(sections) + '<p><a href="manifest.json">Source hashes and camera/evidence manifest</a></p></main></html>'
    (args.out / "index.html").write_text(page, encoding="utf-8")
    print(f"Gallery: {args.out / 'index.html'} ({len(results)} layouts)")


if __name__ == "__main__":
    main()
