"""
AETHERWILD - Generateur de terrain (heightmap 16 bits pour Landscape UE5)
=========================================================================
Produit une ile-continent de ~8 km x 8 km :
  * oceans au sud et a l'ouest, plages
  * grandes plaines centrales et collines boisees
  * chaine de montagnes au nord avec sommets enneiges (~900 m)
  * volcan au nord-est (caldeira)
  * grand lac central + riviere qui descend jusqu'a la mer
  * erosion hydraulique (gouttes vectorisees) + erosion thermique

Sorties :
  Art/Terrain/Aetherwild_Heightmap_4033.png   (16 bits, a importer dans Landscape)
  Art/Terrain/Aetherwild_Heightmap_2017.png   (version legere pour PC modestes)
  Docs/previews/terrain_preview.png           (relief ombre + biomes)
  Content/Data/world.json                     (parametres d'import, niveau de la mer,
                                               points d'apparition par biome, sanctuaires)

Usage : python generate_terrain.py [--seed 7] [--res 4033]
Dependances : numpy, scipy, pillow
"""
import argparse
import json
import math
import os
import time

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))

H_MIN, H_RANGE = -80.0, 1024.0          # metres representables (Z scale 200)
SCALE_XY = 200.0                         # cm par sommet (4033 -> 8.06 km)
Z_SCALE = 200.0


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def value_noise(n, freq, rng):
    g = rng.random((freq + 3, freq + 3)).astype(np.float32)
    z = ndimage.zoom(g, (n + 2 * n / freq) / (freq + 3), order=3)
    o = int(n / freq)
    return z[o:o + n, o:o + n]


def fbm(n, rng, base=4, octaves=7, persistence=0.5, ridged=False):
    out = np.zeros((n, n), np.float32)
    amp, tot, f = 1.0, 0.0, base
    for _ in range(octaves):
        if f > n / 2:
            break
        v = value_noise(n, f, rng)
        if ridged:
            v = 1.0 - np.abs(2 * v - 1)
            v = v * v
        out += v * amp
        tot += amp
        amp *= persistence
        f *= 2
    return out / tot


def bilinear(hm, x, y):
    n = hm.shape[0]
    ix = np.clip(x.astype(np.int32), 0, n - 2)
    iy = np.clip(y.astype(np.int32), 0, n - 2)
    fx, fy = x - ix, y - iy
    h00, h10 = hm[iy, ix], hm[iy, ix + 1]
    h01, h11 = hm[iy + 1, ix], hm[iy + 1, ix + 1]
    gx = (h10 - h00) * (1 - fy) + (h11 - h01) * fy
    gy = (h01 - h00) * (1 - fx) + (h11 - h10) * fx
    h = h00 * (1 - fx) * (1 - fy) + h10 * fx * (1 - fy) + h01 * (1 - fx) * fy + h11 * fx * fy
    return h, gx, gy, ix, iy, fx, fy


def hydraulic_erosion(hm, rng, droplets=400_000, batch=50_000, steps=48):
    """Erosion par gouttes (algorithme classique), vectorisee sur des lots de gouttes."""
    n = hm.shape[0]
    inertia, cap_f, min_cap, erode_s, depo_s, evap, grav = 0.05, 4.0, 0.01, 0.3, 0.3, 0.015, 4.0
    for b in range(droplets // batch):
        delta = np.zeros_like(hm)
        x = rng.random(batch, dtype=np.float32) * (n - 2)
        y = rng.random(batch, dtype=np.float32) * (n - 2)
        dx = np.zeros(batch, np.float32)
        dy = np.zeros(batch, np.float32)
        speed = np.ones(batch, np.float32)
        water = np.ones(batch, np.float32)
        sed = np.zeros(batch, np.float32)
        alive = np.ones(batch, bool)
        cur = hm + delta
        for _ in range(steps):
            h, gx, gy, ix, iy, fx, fy = bilinear(cur, x, y)
            dx = dx * inertia - gx * (1 - inertia)
            dy = dy * inertia - gy * (1 - inertia)
            ln = np.sqrt(dx * dx + dy * dy) + 1e-9
            dx /= ln
            dy /= ln
            nx, ny = x + dx, y + dy
            alive &= (nx > 0) & (nx < n - 2) & (ny > 0) & (ny < n - 2) & (ln > 1e-6)
            nh = bilinear(cur, np.clip(nx, 0, n - 2), np.clip(ny, 0, n - 2))[0]
            dh = nh - h
            cap = np.maximum(-dh * speed * water * cap_f, min_cap)
            depositing = (sed > cap) | (dh > 0)
            dep = np.where(dh > 0, np.minimum(dh, sed), (sed - cap) * depo_s)
            ero = np.minimum((cap - sed) * erode_s, -dh)
            amt = np.where(depositing, dep, -ero) * alive          # + depose, - erode
            sed = sed - amt
            w = [(iy, ix, (1 - fx) * (1 - fy)), (iy, ix + 1, fx * (1 - fy)),
                 (iy + 1, ix, (1 - fx) * fy), (iy + 1, ix + 1, fx * fy)]
            for (yy, xx, ww) in w:
                np.add.at(delta, (yy, xx), amt * ww)
            speed = np.sqrt(np.maximum(speed * speed + dh * grav, 0))
            water *= (1 - evap)
            x, y = np.where(alive, nx, x), np.where(alive, ny, y)
        hm += ndimage.gaussian_filter(delta, 0.9)
        print("   erosion lot %d/%d" % (b + 1, droplets // batch))
    return hm


def thermal_erosion(hm, iters=30, talus=0.9, k=0.25):
    for _ in range(iters):
        for sh in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            nb = np.roll(hm, sh, axis=(0, 1))
            d = hm - nb
            m = np.where(d > talus, (d - talus) * k * 0.5, 0)
            hm -= m
            hm += np.roll(m, (-sh[0], -sh[1]), axis=(0, 1))
    return hm


def polyline_distance(n, pts, rng, meander=0.012):
    """Distance (en pixels) a une riviere sinueuse definie par des points normalises."""
    dense = []
    for (a, b) in zip(pts[:-1], pts[1:]):
        a, b = np.array(a), np.array(b)
        seg = np.linalg.norm(b - a)
        k = max(2, int(seg * n * 1.5))
        nrm = np.array([-(b - a)[1], (b - a)[0]]) / (seg + 1e-9)
        ph = rng.random() * 6.28
        for t in np.linspace(0, 1, k):
            off = meander * math.sin(t * 6.28 * 3 * seg * 4 + ph) * math.sin(math.pi * t)
            dense.append(a + (b - a) * t + nrm * off)
    mask = np.ones((n, n), bool)
    for p in dense:
        x, y = int(p[0] * (n - 1)), int(p[1] * (n - 1))
        mask[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = False
    return ndimage.distance_transform_edt(mask)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--res', type=int, default=4033)
    ap.add_argument('--coarse', type=int, default=1025)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    t0 = time.time()
    N = a.coarse
    cell_m = SCALE_XY / 100.0 * (a.res - 1) / (N - 1)        # metres par pixel grossier
    v, u = np.mgrid[0:N, 0:N].astype(np.float32) / (N - 1)

    print("1) Forme generale")
    warp = (fbm(N, rng, 3, 4) - 0.5) * 0.08
    uu, vv = u + warp, v + (fbm(N, rng, 3, 4) - 0.5) * 0.08
    land = smoothstep(0.98, 0.80, vv) * smoothstep(0.0, 0.12, uu) * smoothstep(1.0, 0.93, uu) * smoothstep(0.0, 0.05, vv)
    hills = fbm(N, rng, 4, 7, 0.5)
    plains = 6 + 22 * fbm(N, rng, 8, 6, 0.55) + 70 * smoothstep(0.45, 0.8, hills)
    ridges = fbm(N, rng, 5, 8, 0.5, ridged=True)
    mount_mask = np.maximum(smoothstep(0.42, 0.12, vv), smoothstep(0.70, 0.92, uu) * smoothstep(0.75, 0.35, vv))
    mount_mask *= smoothstep(0.02, 0.10, vv)
    mountains = 140 + 1350 * ridges ** 1.35 * (0.55 + 0.45 * fbm(N, rng, 3, 3))
    h = plains * (1 - mount_mask) + np.maximum(plains, mountains) * mount_mask

    # volcan
    vc = np.array([0.80, 0.30])
    d = np.sqrt((u - vc[0]) ** 2 + (v - vc[1]) ** 2)
    cone = 680 * np.clip(1 - d / 0.16, 0, 1) ** 1.6
    crater = 140 * np.exp(-(d / 0.018) ** 2)
    h = np.maximum(h, cone - crater + 40 * (fbm(N, rng, 16, 4) - 0.5) * (d < 0.16))

    # lac central
    lc = np.array([0.36, 0.55])
    lw = (fbm(N, rng, 5, 4) - 0.5) * 0.09
    dl = np.sqrt(((u + lw - lc[0]) / 1.35) ** 2 + ((v - lw * 0.7 - lc[1]) / 0.9) ** 2) + (fbm(N, rng, 9, 4) - 0.5) * 0.05
    h = h - smoothstep(0.10, 0.02, dl) * (h + 22)

    # ocean
    h = h * land + (1 - land) * (-60 + 20 * fbm(N, rng, 6, 4))
    h = h - smoothstep(0.35, 0.0, land) * 15

    print("2) Erosion hydraulique (%.1f m/pixel)" % cell_m)
    hn = (h / 1000.0).astype(np.float32)
    hn = hydraulic_erosion(hn, rng)
    hn = thermal_erosion(hn, iters=20, talus=0.9 * cell_m / 1000.0)
    h = hn * 1000.0

    print("3) Sur-echantillonnage %d -> %d + details" % (N, a.res))
    R = a.res
    H = ndimage.zoom(h, R / N, order=3)[:R, :R].astype(np.float32)
    mm = ndimage.zoom(mount_mask.astype(np.float32), R / N, order=1)[:R, :R]
    detail = (fbm(R, rng, 64, 5, 0.5) - 0.5)
    H += detail * (1.5 + 14 * mm + 4 * smoothstep(20, 200, H))

    # riviere (du pied des montagnes au lac puis a la mer)
    print("4) Riviere")
    river_pts = [(0.58, 0.30), (0.52, 0.40), (0.44, 0.50), (0.37, 0.55),
                 (0.33, 0.63), (0.38, 0.74), (0.44, 0.84), (0.47, 0.97)]
    dist = polyline_distance(R, river_pts, rng)
    w = 14.0                                                 # ~28 m de large
    bed = -3.5 + 3.0 * (dist / w) ** 2
    valley = smoothstep(w, w * 8, dist)
    Hr = np.minimum(H, np.where(dist < w, bed, H))
    target = np.minimum(H, 2.0 + 0.05 * (dist - w) * 2.0)
    H = np.where(dist < w, Hr, H * valley + target * (1 - valley))

    H = np.clip(H, H_MIN + 1, H_MIN + H_RANGE - 1)
    print("   altitude min %.1f m  max %.1f m" % (H.min(), H.max()))

    # ------------------------------------------------------------------ export
    out_dir = os.path.join(ROOT, 'Art', 'Terrain')
    os.makedirs(out_dir, exist_ok=True)
    q = np.round((H - H_MIN) / H_RANGE * 65535).astype(np.uint16)
    Image.fromarray(q).save(os.path.join(out_dir, 'Aetherwild_Heightmap_%d.png' % R))
    small = ndimage.zoom(H, 2017 / R, order=1)[:2017, :2017]
    Image.fromarray(np.round((small - H_MIN) / H_RANGE * 65535).astype(np.uint16)).save(
        os.path.join(out_dir, 'Aetherwild_Heightmap_2017.png'))
    chk = np.array(Image.open(os.path.join(out_dir, 'Aetherwild_Heightmap_%d.png' % R)))
    assert chk.dtype == np.uint16 and chk.shape == (R, R), (chk.dtype, chk.shape)

    # ------------------------------------------------------------------ biomes
    print("5) Biomes + points d'apparition")
    step = 4
    Hs = H[::step, ::step]
    gy, gx = np.gradient(Hs, SCALE_XY / 100.0 * step)
    slope = np.degrees(np.arctan(np.sqrt(gx * gx + gy * gy)))
    forest_n = ndimage.zoom(fbm(N, np.random.default_rng(a.seed + 99), 6, 5), Hs.shape[0] / N, order=1)[:Hs.shape[0], :Hs.shape[1]]
    vs, us = np.mgrid[0:Hs.shape[0], 0:Hs.shape[1]] / (Hs.shape[0] - 1)
    dvol = np.sqrt((us - vc[0]) ** 2 + (vs - vc[1]) ** 2)
    water = Hs < 0
    near_water = ndimage.binary_dilation(water, iterations=12) & ~water
    biome = np.full(Hs.shape, 'Plains', dtype=object)
    biome[(forest_n > 0.52) & (Hs < 320)] = 'Forest'
    biome[(Hs > 220) | (slope > 32)] = 'Mountains'
    biome[Hs > 600] = 'Peaks'
    biome[(dvol < 0.12) & (Hs > 60)] = 'Volcano'
    biome[near_water & (Hs < 8)] = 'Shore'
    biome[water] = 'Water'

    colors = {'Water': (40, 90, 140), 'Shore': (214, 200, 150), 'Plains': (126, 160, 80), 'Forest': (52, 100, 50),
              'Mountains': (125, 115, 100), 'Peaks': (240, 245, 250), 'Volcano': (90, 50, 40)}
    rgb = np.zeros(Hs.shape + (3,), np.float32)
    for k, c in colors.items():
        rgb[biome == k] = c
    # ombrage
    ls = np.clip(0.55 + 0.45 * ((-gx - gy) / np.sqrt(gx * gx + gy * gy + 1.0)), 0.25, 1.2)
    deep = np.clip(-Hs / 60.0, 0, 1)
    rgb[water] = (rgb[water] * (1 - 0.5 * deep[water][:, None]))
    rgb[~water] *= ls[~water][:, None]
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))

    rngp = np.random.default_rng(a.seed + 5)
    half = (R - 1) * SCALE_XY / 2.0

    def to_world(iy, ix):
        x = -half + ix * step * SCALE_XY
        y = -half + iy * step * SCALE_XY
        return [round(float(x), 1), round(float(y), 1), round(float(Hs[iy, ix] * 100.0), 1)]

    quotas = {'Plains': 34, 'Forest': 30, 'Mountains': 24, 'Peaks': 10, 'Volcano': 10, 'Shore': 22, 'Water': 14}
    min_d = {'Plains': 70, 'Forest': 60, 'Mountains': 60, 'Peaks': 40, 'Volcano': 30, 'Shore': 40, 'Water': 60}
    spawners = []
    for bname, qn in quotas.items():
        cand = np.argwhere(biome == bname)
        if bname == 'Water':
            coastal = ndimage.binary_dilation(~water, iterations=60)
            cand = cand[(Hs[cand[:, 0], cand[:, 1]] < -4) & coastal[cand[:, 0], cand[:, 1]]]
        rngp.shuffle(cand)
        chosen = []
        for (iy, ix) in cand:
            if len(chosen) >= qn:
                break
            if all((iy - cy) ** 2 + (ix - cx) ** 2 > min_d[bname] ** 2 for cy, cx in chosen):
                chosen.append((iy, ix))
        for (iy, ix) in chosen:
            p = to_world(iy, ix)
            if bname == 'Water':
                p[2] = 0.0
            spawners.append({'biome': bname, 'location': p, 'radius': 4500.0 if bname != 'Water' else 6000.0,
                             'maxAlive': 4 if bname not in ('Peaks', 'Volcano') else 3})

    # sanctuaires : sur des zones plates bien reparties
    flat = np.argwhere((slope < 6) & (Hs > 4) & (Hs < 400) & ~np.isin(biome, ['Water', 'Shore']))
    rngp.shuffle(flat)
    shrines = []
    for (iy, ix) in flat:
        if len(shrines) >= 9:
            break
        if all((iy - a_) ** 2 + (ix - b_) ** 2 > 220 ** 2 for a_, b_ in shrines):
            shrines.append((iy, ix))
    # depart joueur : plaine pres du lac, au sud-ouest du centre
    target = np.array([0.43, 0.66]) * (Hs.shape[0] - 1)
    cand = np.argwhere((biome == 'Plains') & (slope < 5))
    start = cand[np.argmin(((cand - target[::-1]) ** 2).sum(1))]
    shrines.insert(0, tuple(start + np.array([0, 12])))

    from PIL import ImageDraw
    dr = ImageDraw.Draw(img)
    for s_ in spawners:
        ix = (s_['location'][0] + half) / SCALE_XY / step
        iy = (s_['location'][1] + half) / SCALE_XY / step
        dr.ellipse([ix - 3, iy - 3, ix + 3, iy + 3], outline=(255, 60, 60))
    for (iy, ix) in shrines:
        dr.rectangle([ix - 4, iy - 4, ix + 4, iy + 4], fill=(120, 240, 255))
    dr.ellipse([start[1] - 6, start[0] - 6, start[1] + 6, start[0] + 6], fill=(255, 230, 0))
    prev = os.path.join(ROOT, 'Docs', 'previews')
    os.makedirs(prev, exist_ok=True)
    img.resize((1008, 1008), Image.LANCZOS).save(os.path.join(prev, 'terrain_preview.png'))

    landscape_z = -((0 - H_MIN) / H_RANGE * 65535 - 32768) * Z_SCALE / 128.0
    world = {
        "_comment": "Genere par Tools/Terrain/generate_terrain.py - ne pas editer a la main (sauf playerStart).",
        "landscape": {
            "heightmap": "Art/Terrain/Aetherwild_Heightmap_%d.png" % R,
            "resolution": R,
            "location": [-half, -half, round(landscape_z, 2)],
            "scale": [SCALE_XY, SCALE_XY, Z_SCALE],
            "sectionSize": 63, "sectionsPerComponent": 2, "components": (R - 1) // 126,
            "sizeKm": round((R - 1) * SCALE_XY / 100000.0, 2)
        },
        "landscapeLowSpec": {"heightmap": "Art/Terrain/Aetherwild_Heightmap_2017.png", "resolution": 2017,
                             "scale": [SCALE_XY * 2, SCALE_XY * 2, Z_SCALE], "location": [-half, -half, round(landscape_z, 2)],
                             "sectionSize": 63, "sectionsPerComponent": 2, "components": 16},
        "seaLevelZ": 0.0,
        "playerStart": to_world(int(start[0]), int(start[1])),
        "shrines": [to_world(int(iy), int(ix)) for (iy, ix) in shrines],
        "spawners": spawners,
        "volcano": [round(float(-half + vc[0] * (R - 1) * SCALE_XY), 1), round(float(-half + vc[1] * (R - 1) * SCALE_XY), 1)],
    }
    with open(os.path.join(ROOT, 'Content', 'Data', 'world.json'), 'w') as f:
        json.dump(world, f, indent=1)
    counts = {k: int((biome == k).sum()) for k in colors}
    tot = sum(counts.values())
    print("   biomes : " + ", ".join("%s %.0f%%" % (k, 100 * c / tot) for k, c in counts.items()))
    print("   %d spawners, %d sanctuaires, landscape Z = %.1f cm" % (len(spawners), len(shrines), landscape_z))
    print("Termine en %.0f s" % (time.time() - t0))


if __name__ == '__main__':
    main()
