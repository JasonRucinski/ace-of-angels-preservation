"""Render a textured OBJ (as written by tools/gob2obj.py) to a PNG preview.

Usage:
    python -I tools/render_obj.py <model.obj> <out.png> [size] [yaw_deg] [pitch_deg]

Pure standard library: orthographic camera, z-buffer, per-pixel texture
lookup (nearest) from the PNG named by each material's map_Kd in the MTL, Lambert shading from
the face normal. Meant for eyeballing converted geometry, not for beauty.
"""
import math
import argparse
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_assets import png  # noqa: E402


def read_png(path):
    data = Path(path).read_bytes()
    pos, w, h, idat = 8, 0, 0, b""
    while pos < len(data):
        n = struct.unpack_from(">I", data, pos)[0]
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack_from(">IIBB", body)
            if (depth, ctype) != (8, 6):
                raise ValueError("expected RGBA8 PNG (as written by export_assets.py)")
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    raw, stride, rows, prev = zlib.decompress(idat), w * 4, [], bytearray(w * 4)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b, c = prev[i], prev[i - 4] if i >= 4 else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(bytes(line))
        prev = line
    return w, h, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("obj", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("size", type=int, nargs="?", default=512)
    parser.add_argument("yaw", type=float, nargs="?", default=35)
    parser.add_argument("pitch", type=float, nargs="?", default=25)
    parser.add_argument("--focus", help="frame objects whose names start with this prefix; surrounding geometry may be cropped")
    args = parser.parse_args()
    obj, out, size = args.obj, args.out, args.size
    yaw, pitch = math.radians(args.yaw), math.radians(args.pitch)
    focus, object_name = [], ""
    V, T, F, texs, cur = [], [], [], {}, None
    for line in obj.read_text().splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "v":
            if args.focus and object_name.casefold().startswith(args.focus.casefold()):
                focus.append(len(V))
            V.append(tuple(map(float, p[1:4])))
        elif p[0] == "o":
            object_name = line[2:].strip()
        elif p[0] == "vt":
            T.append(tuple(map(float, p[1:3])))
        elif p[0] == "f":
            F.append(([tuple(int(x) - 1 for x in q.split("/")[:2]) for q in p[1:4]], cur))
        elif p[0] == "usemtl":
            cur = p[1]
        elif p[0] == "mtllib":
            name = None
            for m in (obj.parent / p[1]).read_text().splitlines():
                if m.startswith("newmtl"):
                    name = m.split(None, 1)[1]
                elif m.startswith("map_Kd"):
                    f = obj.parent / m.split(None, 1)[1]
                    texs[name] = read_png(f) if f.exists() else None
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)

    def view(x, y, z):
        x, z = x * cy - z * sy, x * sy + z * cy      # yaw about Y
        y, z = y * cp - z * sp, y * sp + z * cp      # pitch about X
        return x, y, z
    P = [view(*v) for v in V]
    if args.focus and not focus:
        raise ValueError(f"no geometry matches focus prefix {args.focus!r}")
    framed = [P[i] for i in focus] if args.focus else P
    xs, ys = [p[0] for p in framed], [p[1] for p in framed]
    scale = 0.9 * size / max(max(xs) - min(xs), max(ys) - min(ys))
    cx, cyy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    S = [((x - cx) * scale + size / 2, size / 2 - (y - cyy) * scale, z) for x, y, z in P]
    img = [bytearray(b"\x20\x20\x28\xff" * size) for _ in range(size)]
    zbuf = [[1e30] * size for _ in range(size)]
    light = (0.4, 0.7, -0.6)
    for tri, mat in F:
        tex = texs.get(mat)
        (a, ta), (b, tb), (c, tc) = tri
        pa, pb, pc = S[a], S[b], S[c]
        area = (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pc[0] - pa[0]) * (pb[1] - pa[1])
        if abs(area) < 1e-9:
            continue
        e1 = [P[b][k] - P[a][k] for k in range(3)]
        e2 = [P[c][k] - P[a][k] for k in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        ln = math.sqrt(sum(k * k for k in n)) or 1
        shade = 0.35 + 0.65 * abs(sum(n[k] * light[k] for k in range(3)) / ln)
        x0, x1 = max(0, int(min(pa[0], pb[0], pc[0]))), min(size - 1, int(max(pa[0], pb[0], pc[0])) + 1)
        y0, y1 = max(0, int(min(pa[1], pb[1], pc[1]))), min(size - 1, int(max(pa[1], pb[1], pc[1])) + 1)
        for py in range(y0, y1 + 1):
            for px in range(x0, x1 + 1):
                w0 = ((pb[0] - px) * (pc[1] - py) - (pc[0] - px) * (pb[1] - py)) / area
                w1 = ((pc[0] - px) * (pa[1] - py) - (pa[0] - px) * (pc[1] - py)) / area
                w2 = 1 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                z = w0 * pa[2] + w1 * pb[2] + w2 * pc[2]
                if z >= zbuf[py][px]:
                    continue
                zbuf[py][px] = z
                r = g = bl = 200
                if tex and T:
                    u = w0 * T[ta][0] + w1 * T[tb][0] + w2 * T[tc][0]
                    v = w0 * T[ta][1] + w1 * T[tb][1] + w2 * T[tc][1]
                    tw, th, rows = tex
                    if u != u or v != v:
                        u = v = 0.0
                    tx, ty = int((u % 1) * tw) % tw, int(((1 - v) % 1) * th) % th
                    r, g, bl = rows[ty][tx * 4:tx * 4 + 3]
                img[py][px * 4:px * 4 + 3] = bytes((int(r * shade), int(g * shade), int(bl * shade)))
    out.write_bytes(png(size, size, [bytes(r) for r in img]))
    print(f"rendered {len(F)} triangles -> {out}")


if __name__ == "__main__":
    main()
