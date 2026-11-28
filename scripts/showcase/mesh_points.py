#!/usr/bin/env python3
"""Turn generated 3D models into small coloured point clouds for the scenes.

A model from the 3D service is a GLB of about half a million triangles and
17 MB: far too heavy for a homepage. This samples points evenly over its
surface, reads each point's colour from the model's own texture, and writes
`frontend/public/scenes/models/<id>.pts` (about 9 bytes a point), the picture
the model was made from as `<id>.webp`, and `index.json` describing where
each one came from.

    scripts/showcase/mesh_points.py --instance local grumpy-cat=670 castle=676

Each argument is `<id>=<request id>` of a finished 3D request on that
deployment. Needs `cwebp` and `dwebp` (or `magick` for PNG/JPEG textures) on PATH.
Standard library only.

File layout (little endian): "ICPT", uint32 count, count*3 int16 positions
(the model centred and scaled so its longest side spans -32767..32767, Y up),
count*3 uint8 sRGB colours. Points are in random order, so any prefix of the
file is itself an even sample.
"""

import argparse
import array
import bisect
import json
import os
import random
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate import ROOT, Club, say  # noqa: E402

OUT = os.path.join(ROOT, "frontend", "public", "scenes", "models")
FLOAT, UINT32, UINT16 = 5126, 5125, 5123


def read_glb(blob):
    magic, _, _ = struct.unpack_from("<4sII", blob, 0)
    if magic != b"glTF":
        raise ValueError("not a GLB file")
    n, _ = struct.unpack_from("<II", blob, 12)
    doc = json.loads(blob[20:20 + n])
    m, _ = struct.unpack_from("<II", blob, 20 + n)
    return doc, memoryview(blob)[28 + n:28 + n + m]


def accessor(doc, binary, index):
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    if view.get("byteStride"):
        raise ValueError("interleaved buffers are not handled")
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}[acc["type"]]
    code = {FLOAT: "f", UINT32: "I", UINT16: "H"}[acc["componentType"]]
    out = array.array(code)
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    out.frombytes(binary[start:start + acc["count"] * width * out.itemsize])
    return out


def texture(doc, binary):
    """The base-colour texture as (width, height, RGB bytes), or None."""
    try:
        mat = doc["materials"][doc["meshes"][0]["primitives"][0]["material"]]
        tex = doc["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
        src = (tex.get("extensions", {}).get("EXT_texture_webp") or tex)["source"]
        image = doc["images"][src]
        view = doc["bufferViews"][image["bufferView"]]
    except (KeyError, IndexError):
        return None
    start = view.get("byteOffset", 0)
    with tempfile.TemporaryDirectory() as tmp:
        raw, ppm = os.path.join(tmp, "t.img"), os.path.join(tmp, "t.ppm")
        open(raw, "wb").write(binary[start:start + view["byteLength"]])
        cmd = ["dwebp", "-quiet", raw, "-ppm", "-o", ppm] if image.get("mimeType") == "image/webp" \
            else ["magick", raw, "-depth", "8", ppm]
        subprocess.run(cmd, check=True, capture_output=True)
        data = open(ppm, "rb").read()
    # P6\n<w> <h>\n255\n<bytes>
    parts = data.split(b"\n", 3)
    w, h = (int(x) for x in parts[1].split())
    return w, h, parts[3]


def sample(blob, count, seed=1):
    doc, binary = read_glb(blob)
    prim = doc["meshes"][0]["primitives"][0]
    pos = accessor(doc, binary, prim["attributes"]["POSITION"])
    uv = accessor(doc, binary, prim["attributes"]["TEXCOORD_0"]) if "TEXCOORD_0" in prim["attributes"] else None
    idx = accessor(doc, binary, prim["indices"])
    tex = texture(doc, binary) if uv else None
    faces = len(idx) // 3

    # Cumulative triangle areas, so bigger triangles get more points.
    total, cumulative = 0.0, array.array("d", bytes(8 * faces))
    for f in range(faces):
        a, b, c = idx[f * 3] * 3, idx[f * 3 + 1] * 3, idx[f * 3 + 2] * 3
        ux, uy, uz = pos[b] - pos[a], pos[b + 1] - pos[a + 1], pos[b + 2] - pos[a + 2]
        vx, vy, vz = pos[c] - pos[a], pos[c + 1] - pos[a + 1], pos[c + 2] - pos[a + 2]
        cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        total += (cx * cx + cy * cy + cz * cz) ** 0.5
        cumulative[f] = total

    lo = [min(pos[k::3]) for k in range(3)]
    hi = [max(pos[k::3]) for k in range(3)]
    mid = [(lo[k] + hi[k]) / 2 for k in range(3)]
    scale = 2 / max(hi[k] - lo[k] for k in range(3))

    rnd = random.Random(seed)
    xyz, rgb = array.array("h"), bytearray()
    for _ in range(count):
        f = bisect.bisect_left(cumulative, rnd.random() * total)
        a, b, c = idx[f * 3], idx[f * 3 + 1], idx[f * 3 + 2]
        r1, r2 = rnd.random(), rnd.random()
        if r1 + r2 > 1:
            r1, r2 = 1 - r1, 1 - r2
        r0 = 1 - r1 - r2
        for k in range(3):
            v = r0 * pos[a * 3 + k] + r1 * pos[b * 3 + k] + r2 * pos[c * 3 + k]
            xyz.append(max(-32767, min(32767, round((v - mid[k]) * scale * 32767))))
        if tex:
            w, h, pixels = tex
            u = r0 * uv[a * 2] + r1 * uv[b * 2] + r2 * uv[c * 2]
            v = r0 * uv[a * 2 + 1] + r1 * uv[b * 2 + 1] + r2 * uv[c * 2 + 1]
            px = min(w - 1, max(0, int(u % 1 * w)))
            py = min(h - 1, max(0, int(v % 1 * h)))
            rgb += pixels[(py * w + px) * 3:(py * w + px) * 3 + 3]
        else:
            rgb += b"\xc8\xc8\xc8"
    if sys.byteorder != "little":
        xyz.byteswap()
    return b"ICPT" + struct.pack("<I", count) + xyz.tobytes() + bytes(rgb), faces


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", "-I", required=True)
    ap.add_argument("--points", type=int, default=16000)
    ap.add_argument("models", nargs="+", help="<id>=<request id>")
    a = ap.parse_args()

    club = Club(a.instance)
    os.makedirs(OUT, exist_ok=True)
    index_path = os.path.join(OUT, "index.json")
    index = json.load(open(index_path)) if os.path.exists(index_path) else {"models": []}
    by_id = {m["id"]: m for m in index["models"]}
    for spec in a.models:
        name, rid = spec.split("=")
        d = club.call("GET", f"/api/inference/requests/{rid}/")
        if not d.get("model_url"):
            say(f"  FAIL  {name}: request {rid} has no model")
            continue
        blob = club.call("GET", d["model_url"], raw=True)
        data, faces = sample(blob, a.points)
        open(os.path.join(OUT, f"{name}.pts"), "wb").write(data)
        # The picture the model was made from, for scenes that show both.
        image = None
        if d.get("input_image_url"):
            raw = os.path.join(OUT, f"{name}.src")
            open(raw, "wb").write(club.call("GET", d["input_image_url"], raw=True))
            subprocess.run(["cwebp", "-quiet", "-q", "80", "-resize", "480", "0", raw, "-o",
                            os.path.join(OUT, f"{name}.webp")], check=True, capture_output=True)
            os.remove(raw)
            image = f"{name}.webp"
        host = d.get("host") or {}
        gpus = [host["gpu"]] if host.get("gpu") else host.get("gpus") or []
        by_id[name] = {
            "id": name, "src": f"{name}.pts", "image": image, "points": a.points, "triangles": faces,
            "model": d.get("model_name"), "seed": (d.get("mesh") or {}).get("seed"),
            "gpu": gpus[0].get("model") if gpus else None,
            "seconds": round((d.get("latency_ms") or 0) / 1000, 1) or None,
        }
        say(f"  made  {name} from request {rid}: {faces} triangles -> {a.points} points, {len(data) // 1024} KB")
    index["models"] = list(by_id.values())
    json.dump(index, open(index_path, "w"), indent=1)
    open(index_path, "a").write("\n")


if __name__ == "__main__":
    main()
