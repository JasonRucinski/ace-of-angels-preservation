"""Build a local comparison from a ReShade same-frame Before/After PNG pair.

Usage: python -I tools/compare_classic_capture.py game/classic-enhanced/comparison-captures
Print Screen in the experiment writes both images and a copy of the preset.
The original PNG bytes are copied unchanged; no simulated filter or retouching.
"""
import argparse
import configparser
import hashlib
import html
import json
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]


def latest_pair(folder):
    pairs = [(before, before.with_name(before.name.removesuffix("_Before.png") + "_After.png"))
             for before in folder.glob("AOA_*_Before.png")]
    pairs = [(before, after) for before, after in pairs if after.is_file()]
    if not pairs:
        raise ValueError("no complete capture pair; enter flight with effects enabled and press Print Screen")
    return max(pairs, key=lambda pair: pair[1].stat().st_mtime_ns)


def build(before, after, output, *, sequential_ui=False):
    if output.exists():
        raise ValueError("output already exists; select a new folder to preserve earlier captures")
    if sequential_ui and not (before.name.endswith("_UIOriginal.png") and after.name.endswith("_UIProtected.png")):
        raise ValueError("expected the UI add-on's original/protected captures")
    if not sequential_ui and before.name.removesuffix("_Before.png") != after.name.removesuffix("_After.png"):
        raise ValueError("the two files are not a matching same-frame capture pair")
    with Image.open(before) as source, Image.open(after) as enhanced:
        source.load()
        enhanced.load()
        if source.size != enhanced.size:
            raise ValueError("capture dimensions differ")
        width, height = source.size
        difference = ImageChops.difference(source.convert("RGB"), enhanced.convert("RGB"))
        channels = difference.split()
        maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        changed = width * height - maximum.histogram()[0]
        if changed == 0:
            raise ValueError("images are identical; check that Classic Enhanced is enabled")
        mean_difference = sum(ImageStat.Stat(difference).mean) / 3
    preset = after.with_suffix(".ini")
    if not preset.is_file():
        raise ValueError("capture preset is missing; enable SavePresetFile and take another capture")
    # ReShade's saved preset lets the report prove that the full frame was filtered.
    settings = configparser.ConfigParser(interpolation=None)
    settings.read_string("[PRESET]\n" + preset.read_text(encoding="utf-8-sig"))
    if "ClassicEnhanced@AOAClassic.fx" not in settings.get("PRESET", "Techniques", fallback=""):
        raise ValueError("capture preset did not enable Classic Enhanced")
    if settings.getboolean("AOAClassic.fx", "SplitPreview", fallback=False):
        raise ValueError("split preview was enabled; disable it before capturing a full-frame comparison")
    record = {
        "capture": before.name.removesuffix("_Before.png"),
        "method": ("Consecutive live frames with effects off/on and HUD present; moving objects may differ"
                   if sequential_ui else "ReShade before/after processing of the same rendered frame"),
        "width": width, "height": height,
        "changed_pixels_percent": round(changed * 100 / (width * height), 3),
        "mean_absolute_channel_difference_0_255": round(mean_difference, 4),
        "before_sha256": hashlib.sha256(before.read_bytes()).hexdigest(),
        "after_sha256": hashlib.sha256(after.read_bytes()).hexdigest(),
        "preset": dict(settings["AOAClassic.fx"]),
    }
    output.mkdir(parents=True)
    shutil.copyfile(before, output / "original.png")
    shutil.copyfile(after, output / "enhanced.png")
    shutil.copyfile(preset, output / "capture-preset.ini")
    (output / "comparison.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    page = '''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ace of Angels — Classic Enhanced comparison</title>
<style>
*{box-sizing:border-box}body{margin:0;padding:28px;background:#10151d;color:#e6edf5;font:16px/1.5 system-ui}
main{max-width:1800px;margin:auto}h1{margin:0;font-size:26px}p{color:#aab9c9;margin:8px 0 20px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}figure{margin:0}figcaption{font-weight:650;margin-bottom:8px}
img{display:block;width:100%;height:auto}.stage{position:relative;width:100%;overflow:hidden;background:#000}
.stage .after{position:absolute;inset:0;clip-path:inset(0 0 0 50%)}
.line{position:absolute;top:0;bottom:0;left:50%;width:2px;background:#fff;pointer-events:none}
.controls{display:flex;align-items:center;gap:16px;margin:24px 0 12px}input{flex:1}a{color:#8acbff}
details{margin-top:24px}summary{cursor:pointer}pre{white-space:pre-wrap;color:#aab9c9}
@media(max-width:700px){body{padding:16px}.pair{grid-template-columns:1fr}}
</style><main>
<h1>Classic Enhanced</h1>
<p>Original and enhanced captures of the same frame. No image retouching.<br>__CAPTION__</p>
<div class="pair"><figure><figcaption>Original</figcaption><a href="original.png"><img src="original.png" alt="Original game frame"></a></figure>
<figure><figcaption>Classic Enhanced</figcaption><a href="enhanced.png"><img src="enhanced.png" alt="Same game frame with Classic Enhanced"></a></figure></div>
<div class="controls"><label for="split">Original ← compare → Enhanced</label><input id="split" type="range" min="0" max="100" value="50" aria-label="Comparison divider"></div>
<div class="stage"><img src="original.png" alt="Original frame"><img class="after" id="after" src="enhanced.png" alt="Enhanced frame"><div class="line" id="line"></div></div>
<p>Drag the divider across hull textures, bright effects, and small HUD text. Open either image above for full resolution.</p>
<details><summary>Capture measurements and preset</summary><pre>__RECORD__</pre></details>
</main><script>
document.getElementById('split').addEventListener('input', e => {
document.getElementById('after').style.clipPath = `inset(0 0 0 ${e.target.value}%)`;
document.getElementById('line').style.left = e.target.value + '%';
});</script></html>'''
    if sequential_ui:
        page = page.replace("Original and enhanced captures of the same frame.",
                            "Consecutive live captures with the UI preserved. Moving objects may differ.")
        page = page.replace("Same game frame with Classic Enhanced", "Next game frame with Classic Enhanced")
    caption = f"{width} × {height} · {record['changed_pixels_percent']}% of pixels changed · {record['capture']}"
    page = page.replace("__CAPTION__", html.escape(caption)).replace("__RECORD__", html.escape(json.dumps(record, indent=2)))
    (output / "index.html").write_text(page, encoding="utf-8")
    return {"comparison": str((output / "index.html").resolve()), **record}


def configure(folder):
    """Configure ReShade's screenshot callback; takes effect on the next launch."""
    folder = folder.resolve()
    if not (folder / "_classic_enhanced.json").is_file():
        raise ValueError("configure requires the isolated Classic Enhanced game folder")
    if (folder / "ClassicUI.addon32").is_file():
        raise ValueError("UI mode captures through tools/classic_ui.py capture; final-screen pairs do not include the pre-HUD effect")
    path = folder / "ReShade.ini"
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(path, encoding="utf-8-sig")
    for section in ("INPUT", "SCREENSHOT"):
        if not config.has_section(section):
            config.add_section(section)
    config["INPUT"]["KeyScreenshot"] = "44,0,0,0"
    config["SCREENSHOT"].update({
        "SavePath": ".\\comparison-captures", "FileFormat": "1",
        "FileNaming": "AOA_%Date%_%Time%_%Count%_%BeforeAfter%",
        "SaveBeforeShot": "1", "SaveOverlayShot": "0", "SavePresetFile": "1", "ClearAlpha": "1",
        "PostSaveCommand": sys.executable,
        "PostSaveCommandArguments": f'-I "{Path(__file__).resolve()}" "%TargetPath%"',
        "PostSaveCommandWorkingDirectory": str(ROOT), "PostSaveCommandHideWindow": "1",
    })
    backup = path.with_name("ReShade.ini.before-auto-comparison")
    if not backup.exists():
        shutil.copyfile(path, backup)
    with path.open("w", encoding="utf-8") as stream:
        config.write(stream, space_around_delimiters=False)
    return {"configured": str(folder), "capture_key": "Print Screen",
            "output": str(ROOT / "work/classic-enhanced"), "restart_required_if_renderer_is_running": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path, help="capture folder, After PNG, or game folder with --configure")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--configure", action="store_true", help="enable same-frame capture and automatic report generation")
    args = parser.parse_args()
    try:
        if args.configure:
            print(json.dumps(configure(args.captures), indent=2))
            return
        if args.captures.suffix.lower() == ".png":
            # ReShade invokes the callback once per file. Only After builds a report.
            if args.captures.name.endswith("_Before.png"):
                return
            if not args.captures.name.endswith("_After.png"):
                raise ValueError("expected a ReShade _After.png capture")
            after = args.captures
            before = after.with_name(after.name.removesuffix("_After.png") + "_Before.png")
        else:
            before, after = latest_pair(args.captures)
        output = args.output or ROOT / "work/classic-enhanced" / before.name.removesuffix("_Before.png")
        # Before/After PNGs are saved on separate ReShade worker threads.
        deadline = time.monotonic() + 10
        while True:
            try:
                result = build(before, after, output)
                break
            except (OSError, ValueError) as error:
                if output.exists() or time.monotonic() >= deadline:
                    raise error
                time.sleep(0.2)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Comparison: {error}\n")


if __name__ == "__main__":
    main()
