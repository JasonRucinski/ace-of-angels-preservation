"""Cut the recorded shots into the highlight reel with ffmpeg.

  python -I tools/reel/edit.py tools/reel/edit.json [--raw work/reel/raw] [--out work/reel]
                               [--no-music | --music FILE] [--music-start SECONDS|auto]

edit.json:
  "segments": list of {"clip": "01_name", "in": s, "dur": s} or
              {"card": ["line", ...], "dur": s, "logo": true?, "kicker"?}; an
              empty card is a black beat. Each joins the previous one with a
              dissolve of "dissolve" seconds (default 0.6; "cut": true makes
              it a two-frame cut).
  "titles":   text drawn over the footage: {"text", "sub"?, "kicker"?, "at", "dur",
              "pos": "center"|"lower", "size"?}; "at" is seconds or "@N+s",
              s seconds into segment N, so titles follow re-cut clips
  "style":    "punch" (here or per card/title): heavy letter-spaced capitals,
              a gold kicker line above, quick fades and a slight upward drift;
              otherwise the plain Bahnschrift style.
  "music":    {"file": path, "start": s|"auto"}
Writes reel.mp4 (1920x1080, 60 fps) and reel-720p.mp4 next to a copy of
the filter graph. Fonts come from C:\\Windows\\Fonts.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W, H, FPS = 1920, 1080, 60
FONTS = {"title": "bahnschrift.ttf", "body": "segoeui.ttf", "bold": "segoeuib.ttf", "heavy": "seguibl.ttf"}
CUT = 2 / FPS
GOLD = "#e8c46a"
HAIR = " "


def resolve_time(at, starts):
    """Seconds, or "@N" / "@N+s": s seconds after segment N starts."""
    if isinstance(at, (int, float)):
        return float(at)
    m = re.fullmatch(r"@(\d+)(?:\+([\d.]+))?", at)
    if not m:
        raise ValueError(f"bad title time {at!r}")
    return round(starts[int(m.group(1))] + float(m.group(2) or 0), 4)


def tracked(text, gap=2):
    """Upper case with hair spaces between letters (drawtext has no tracking)."""
    return (HAIR * gap).join(text.upper())


def alpha(start, end, fade=0.5):
    """drawtext alpha: fade in and out over `fade` seconds inside [start, end]."""
    return (f"if(lt(t,{start}),0,if(lt(t,{start + fade}),(t-{start})/{fade},"
            f"if(lt(t,{end - fade}),1,if(lt(t,{end}),({end}-t)/{fade},0))))")


def text_file(work, text):
    """drawtext reads text from a file, which avoids escaping ':' '%' and quotes."""
    work.mkdir(parents=True, exist_ok=True)
    index = len(list(work.glob("t*.txt")))
    path = work / f"t{index:02d}.txt"
    path.write_text(text, encoding="utf-8")
    return path.relative_to(work.parent).as_posix()


def drawtext(work, text, size, y, font="title", color="white", start=None, end=None, fade=0.5, drift=0):
    """drift: pixels the text rises between start and end (needs start/end)."""
    if drift and start is not None:
        y = f"'{y}-{drift}*(t-{start})/{end - start}'"
    border = 3 if font == "heavy" else 2
    parts = [f"fontfile=fonts/{FONTS[font]}", f"textfile={text_file(work, text)}", f"fontsize={size}",
             f"fontcolor={color}", "x=(w-text_w)/2", f"y={y}", f"borderw={border}", "bordercolor=black@0.6",
             "shadowx=0", "shadowy=4", "shadowcolor=black@0.75"]
    if start is not None:
        parts += [f"alpha='{alpha(start, end, fade)}'", f"enable='between(t,{start},{end})'"]
    return "drawtext=" + ":".join(parts)


def punch_card(work, seg, i, inputs):
    """A black card in the punch style; appends the logo input when asked."""
    dur, lines = seg["dur"], seg["card"]
    filters = [f"color=c=black:s={W}x{H}:r={FPS}:d={dur}"]
    if seg.get("logo"):
        inputs += ["-loop", "1", "-framerate", str(FPS), "-t", str(dur), "-i", str(ROOT / "docs/images/logo.jpg")]
        index = sum(1 for a in inputs if a == "-i") - 1
        for n, line in enumerate(lines):
            first = n == 0
            filters.append(drawtext(work, (line if "/" in line else tracked(line, 3 if first else 1)), 84 if first else 38, 640 + n * 74 + (0 if first else 30),
                                    "heavy" if first else "bold", "white" if first else GOLD, 0, dur, 0.2))
        return (f"[{index}:v]scale=-1:420:flags=lanczos,colorlevels=rimin=0.07:gimin=0.07:bimin=0.07,"
                f"format=yuv420p[logo{i}];" + ",".join(filters) + f",format=yuv420p[bg{i}];"
                f"[bg{i}][logo{i}]overlay=(W-w)/2:150,setsar=1")
    if seg.get("kicker"):
        filters.append(drawtext(work, tracked(seg["kicker"], 4), 64, H // 2 - 150, "bold", GOLD, 0, dur, 0.1, 10))
    for line in lines:
        filters.append(drawtext(work, tracked(line), 150, H // 2 - 60, "heavy", "white", 0, dur, 0.1, 18))
    return ",".join(filters) + ",format=yuv420p,setsar=1"


def music_start(path, length):
    """Start of the loudest `length`-second stretch (1 s steps), skipping the first 10 s."""
    run = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                          "ebur128=metadata=1,ametadata=print:key=lavfi.r128.M:file=-", "-f", "null", "-"],
                         capture_output=True, text=True)
    per_second = {}
    t = None
    for line in run.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
        m = re.search(r"lavfi.r128.M=(-?[\d.]+|-inf)", line)
        if m and t is not None and m.group(1) != "-inf":
            per_second.setdefault(int(t), []).append(10 ** (float(m.group(1)) / 10))
    seconds = sorted(per_second)
    energy = {s: sum(v) / len(v) for s, v in per_second.items()}
    best, best_value = 10, -1
    for s in seconds:
        if s < 10 or s + length > seconds[-1]:
            continue
        value = sum(energy.get(s + i, 0) for i in range(int(length)))
        if value > best_value:
            best, best_value = s, value
    return best


def build(edit, raw, out, music, start):
    work = out / "edit"
    if work.exists():
        shutil.rmtree(work)
    (out / "fonts").mkdir(parents=True, exist_ok=True)
    for name in FONTS.values():
        if not (out / "fonts" / name).exists():
            shutil.copy(Path("C:/Windows/Fonts") / name, out / "fonts" / name)
    inputs, chains, count = [], [], 0
    segments = edit["segments"]
    for i, seg in enumerate(segments):
        label = f"s{i}"
        if "clip" in seg:
            inputs += ["-ss", str(seg["in"]), "-t", str(seg["dur"]), "-i", str(raw / f"{seg['clip']}.mp4")]
            count += 1
            chains.append(f"[{count - 1}:v]fps={FPS},scale={W}:{H}:flags=lanczos,setsar=1,"
                          f"format=yuv420p,setpts=PTS-STARTPTS[{label}]")
        elif seg.get("style", edit.get("style")) == "punch":
            chains.append(punch_card(work, seg, i, inputs) + f"[{label}]")
            if seg.get("logo"):
                count += 1
        else:
            lines = seg["card"]
            filters = [f"color=c=black:s={W}x{H}:r={FPS}:d={seg['dur']}"]
            top = H / 2 - (len(lines) * 80) / 2
            if seg.get("logo"):
                inputs += ["-loop", "1", "-framerate", str(FPS), "-t", str(seg["dur"]),
                           "-i", str(ROOT / "docs/images/logo.jpg")]
                count += 1
                chains.append(f"[{count - 1}:v]scale=-1:420:flags=lanczos,colorlevels=rimin=0.07:gimin=0.07:bimin=0.07,format=yuv420p[logo{i}]")
                top = 660
            for n, line in enumerate(lines):
                big = n == 0
                filters.append(drawtext(work, line, 76 if big else 40, int(top + n * 86 + (0 if big else 14)),
                                        "title" if big else "body", "white" if big else "#d8c890"))
            chain = ",".join(filters) + ",format=yuv420p"
            if seg.get("logo"):
                chains.append(f"{chain}[bg{i}]")
                chains.append(f"[bg{i}][logo{i}]overlay=(W-w)/2:180,setsar=1[{label}]")
            else:
                chains.append(f"{chain},setsar=1[{label}]")
    # Chain the dissolves.
    current, length, starts = "s0", segments[0]["dur"], [0.0]
    for i in range(1, len(segments)):
        d = CUT if segments[i].get("cut") else segments[i].get("dissolve", edit.get("dissolve", 0.6))
        offset = round(length - d, 4)
        starts.append(offset)
        chains.append(f"[{current}][s{i}]xfade=transition=fade:duration={d}:offset={offset}[x{i}]")
        current, length = f"x{i}", length - d + segments[i]["dur"]
    titles = []
    for title in edit.get("titles", []):
        s = resolve_time(title["at"], starts)
        e = s + title["dur"]
        if title.get("style", edit.get("style")) == "punch":
            size = title.get("size", 150)
            y = H / 2 - size / 2 if title.get("pos", "center") == "center" else H - 200 - size
            if title.get("kicker"):
                titles.append(drawtext(work, tracked(title["kicker"], 3), 44, int(y - 70), "bold", GOLD,
                                       s, e, 0.12, 14))
            titles.append(drawtext(work, tracked(title["text"]), size, int(y), "heavy", "white", s, e, 0.12, 14))
            if title.get("sub"):
                titles.append(drawtext(work, tracked(title["sub"], 1), 40, int(y + size + 20), "bold", GOLD,
                                       s, e, 0.12, 14))
            continue
        y = H / 2 - 60 if title.get("pos", "lower") == "center" else H - 250
        size = title.get("size", 84)
        titles.append(drawtext(work, title["text"], size, int(y), "title", start=s, end=e, fade=0.45))
        if title.get("sub"):
            titles.append(drawtext(work, title["sub"], 40, int(y + size + 18), "body", "#d8c890", s + 0.2, e, 0.45))
    fade_in = 0.25 if edit.get("style") == "punch" else 0.8
    final = [*titles, f"fade=t=in:st=0:d={fade_in}", f"fade=t=out:st={length - 1.2:.3f}:d=1.2"]
    chains.append(f"[{current}]" + ",".join(final) + "[v]")
    audio_args, audio_map = [], []
    if music:
        if start == "auto":
            start = music_start(music, length)
        audio_args = ["-ss", str(start), "-t", f"{length:.3f}", "-i", str(music)]
        chains.append(f"[{count}:a]afade=t=in:st=0:d=0.6,afade=t=out:st={length - 3:.3f}:d=3,"
                      f"loudnorm=I=-14:TP=-1.5:LRA=11,volume=-2dB,aresample=48000[a]")
        audio_map = ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    graph = ";\n".join(chains)
    (work / "graph.txt").write_text(graph, encoding="utf-8")
    target = out / "reel.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats", "-y", *inputs, *audio_args,
               "-/filter_complex", "edit/graph.txt", "-map", "[v]", *audio_map,
               "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-pix_fmt", "yuv420p",
               "-r", str(FPS), "-movflags", "+faststart", "-t", f"{length:.3f}", str(target.resolve())]
    subprocess.run(command, cwd=out, check=True)
    small = out / "reel-720p.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(target), "-vf",
                    "scale=1280:720:flags=lanczos", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                    "-c:a", "copy", "-movflags", "+faststart", str(small)], check=True)
    return {"reel": str(target), "reel_720p": str(small), "seconds": round(length, 3), "music_start": start}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("edit", type=Path)
    parser.add_argument("--raw", type=Path, default=ROOT / "work/reel/raw")
    parser.add_argument("--out", type=Path, default=ROOT / "work/reel")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--no-music", action="store_true")
    group.add_argument("--music", type=Path)
    parser.add_argument("--music-start")
    args = parser.parse_args()
    edit = json.loads(args.edit.read_text(encoding="utf-8"))
    spec = edit.get("music", {})
    music = None if args.no_music else (args.music or (ROOT / spec["file"] if spec.get("file") else None))
    start = args.music_start or spec.get("start", "auto")
    start = start if start == "auto" else float(start)
    print(json.dumps(build(edit, args.raw.resolve(), args.out.resolve(), music, start), indent=1))


if __name__ == "__main__":
    sys.exit(main())
