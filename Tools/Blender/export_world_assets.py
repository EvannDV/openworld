"""
AETHERWILD - Export des assets "v2" (ceux des rendus de direction artistique) vers Unreal.
Produit Art/EnvironmentV2/*.fbx + Textures/*.png + SM_LavaFlows.fbx (coulees de lave sur le vrai relief).
Usage : python export_world_assets.py [--only nom1,nom2]
"""
import sys, os, math, random, json, argparse, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import bpy, bmesh
import numpy as np
from mathutils import Vector, Matrix, noise
import concept_world as cw
from hero_common import hexc, link, paint, mix, sstep

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "Art", "EnvironmentV2")
TEX = os.path.join(OUT, "Textures")
LEAVES_GAME = 300          # cartes de feuilles par couronne (version jeu, plus legere que les rendus)


def fresh():
    cw.reset(); cw.PENDING.clear(); cw.CARD_CACHE.clear()


def textures():
    os.makedirs(TEX, exist_ok=True)
    spec = {
        "T_Leaf_Green": ([(64, 112, 32), (88, 140, 42), (52, 92, 28), (110, 150, 50)], 1, "leaf"),
        "T_Leaf_Autumn": ([(196, 120, 40), (220, 160, 60), (170, 80, 30)], 3, "leaf"),
        "T_Leaf_Blossom": ([(250, 205, 222), (242, 175, 205), (255, 236, 244)], 2, "petal"),
        "T_Needles": ([(30, 62, 34), (40, 78, 40), (26, 52, 30)], 4, "needle"),
        "T_Fern": ([(60, 110, 40), (75, 125, 45)], 5, "fern"),
    }
    paths = {}
    for name, (pal, seed, kind) in spec.items():
        paths[name] = cw.tex_leaf(os.path.join(TEX, name + ".png"), pal, seed, kind=kind)
    return paths


def realize(root_name, mats_by_card):
    """Fusionne tronc + toutes les cartes de feuilles instanciees en UN seul mesh (slots : 0 ecorce, 1.. feuillages)."""
    for fn in cw.PENDING: fn()
    cw.PENDING.clear()
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    col = bm.loops.layers.color.new("Col"); uvl = bm.loops.layers.uv.new("UVMap")
    slot_of = {}
    slots = ["M_Bark"]
    rnd = random.Random(7)
    zmax = 1.0
    trunks = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith(root_name) and "crown" not in o.name and "tier" not in o.name
              and not o.name.startswith("card_")]
    # tronc(s)
    bark = hexc("#4e3526")
    for t in trunks:
        me = t.evaluated_get(dg).to_mesh()
        mw = t.matrix_world
        vmap = {}
        for v in me.vertices:
            vmap[v.index] = bm.verts.new(mw @ v.co); zmax = max(zmax, (mw @ v.co).z)
        for p in me.polygons:
            try:
                f = bm.faces.new([vmap[i] for i in p.vertices])
            except ValueError:
                continue
            f.material_index = 0
            for lp in f.loops:
                n = noise.noise(lp.vert.co * 3.0)
                lp[col] = (bark[0] * (0.8 + 0.3 * n), bark[1] * (0.8 + 0.3 * n), bark[2] * (0.8 + 0.3 * n), 0.0)
                lp[uvl].uv = (lp.vert.co.x * 0.5 + lp.vert.co.y * 0.5, lp.vert.co.z * 0.25)
        t.evaluated_get(dg).to_mesh_clear()
    # cartes de feuilles
    for inst in dg.object_instances:
        if not inst.is_instance:
            continue
        card = inst.object.original if hasattr(inst.object, "original") else inst.object
        mname = None
        for cname, mn in mats_by_card.items():
            if card.name.startswith(cname):
                mname = mn
        if mname is None:
            continue
        if mname not in slot_of:
            slot_of[mname] = len(slots); slots.append(mname)
        mw = inst.matrix_world.copy()
        me = card.data
        vs = [bm.verts.new(mw @ v.co) for v in me.vertices]
        tint = rnd.uniform(0.8, 1.15); hue = rnd.uniform(-0.06, 0.06)
        f = bm.faces.new(vs)
        f.material_index = slot_of[mname]
        for lp, uv in zip(f.loops, [(0, 0), (1, 0), (1, 1), (0, 1)]):
            lp[uvl].uv = uv
            w = max(0.0, min(1.0, lp.vert.co.z / max(zmax, 1.0)))
            lp[col] = (tint * (1 + hue), tint, tint * (1 - hue), w)
    me = bpy.data.meshes.new(root_name + "_baked"); bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(root_name, me))
    for s in slots:
        ob.data.materials.append(bpy.data.materials.get(s) or bpy.data.materials.new(s))
    return ob


def export(ob, name):
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    ob.name = name
    path = os.path.join(OUT, name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH'}, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', mesh_smooth_type='FACE', colors_type='SRGB', bake_anim=False)
    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    print("[OK] %-28s %8d tris" % (name, tris), flush=True)


def leaf_material(name, tex):
    return cw.card_material(name, tex)


# ------------------------------------------------------------------ assets
def tree_asset(name, seed, kinds, height, tex):
    fresh()
    mats = [leaf_material("M_Leaves_" + k.capitalize(), tex["T_Leaf_" + k.capitalize()]) for k in kinds]
    cw.broadleaf_tree(name, seed, mats, height=height, leaves_per_blob=LEAVES_GAME)
    ob = realize(name, {"card_" + m.name: m.name for m in mats})
    export(ob, "SM_V2_" + name)


def pine_asset(name, seed, height, tex):
    fresh()
    m = leaf_material("M_Needles", tex["T_Needles"])
    old = cw.volume_cards
    cw.volume_cards = lambda em, card, count, sd, size=1.0: old(em, card, int(count * 0.4), sd, size)
    try:
        cw.pine_tree(name, seed, m, height=height)
    finally:
        pass
    ob = realize(name, {"card_" + m.name: m.name})
    cw.volume_cards = old
    export(ob, "SM_V2_" + name)


def dead_asset(name, seed, height):
    fresh()
    m = cw.bark_material("M_Bark")
    t = cw.broadleaf_tree(name, seed, [m], height=height, leaves_per_blob=0, spread=1.2)
    ob = realize(name, {})
    export(ob, "SM_V2_" + name)


def grass_asset(name, seed, base, tip, flowers=None, h=0.42, blades=70, dry=0.15):
    fresh()
    ob = cw.grass_clump(name, seed, blades=blades, h=h, base=base, tip=tip, flowers=flowers, dry=dry)
    ob.data.materials.append(bpy.data.materials.new("M_Grass"))
    export(ob, "SM_V2_" + name)


def fern_asset(name, seed, tex, fronds=7, length=0.9):
    fresh()
    ob = cw.fern_obj(name, leaf_material("M_Fern", tex["T_Fern"]), seed, fronds=fronds, length=length)
    me = ob.data
    attr = me.color_attributes.new("Col", 'BYTE_COLOR', 'CORNER')
    for li, lp in enumerate(me.loops):
        z = me.vertices[lp.vertex_index].co.z
        attr.data[li].color = (1, 1, 1, max(0.0, min(1.0, z / 0.6)))
    export(ob, "SM_V2_" + name)


def rock_asset(name, size, seed, c1, c2, moss=None, flat=0.8):
    fresh()
    ob = cw.rock(name, size, seed, bpy.data.materials.new("M_Rock"), flat=flat)
    a, b = hexc(c1), hexc(c2); mo = hexc(moss) if moss else None
    def fn(co, n):
        t = 0.5 + 0.5 * noise.noise(co * (2.0 / size))
        c = mix(a, b, t)
        if mo is not None:
            c = mix(c, mo, sstep(0.55, 0.85, n.z) * (0.6 + 0.4 * noise.noise(co * (1.0 / size))))
        return (c[0], c[1], c[2], 0.0)
    paint(ob, fn)
    export(ob, "SM_V2_" + name)


def lava_flows():
    """Coulees de lave tracees par descente de gradient sur la vraie heightmap, en coordonnees du monde (metres)."""
    from PIL import Image
    fresh()
    w = json.load(open(os.path.join(ROOT, "Content", "Data", "world.json")))
    L = w["landscape"]
    q = np.array(Image.open(os.path.join(ROOT, L["heightmap"]))).astype(np.float32)
    H = q / 65535 * 1024 - 80                                    # metres (cf. generate_terrain.py)
    step = 4
    Hs = H[::step, ::step]
    n = Hs.shape[0]
    cell = L["scale"][0] / 100.0 * step                         # metres par cellule
    ox, oy = L["location"][0] / 100.0, L["location"][1] / 100.0
    vx, vy = w["volcano"][0] / 100.0, w["volcano"][1] / 100.0
    ci, cj = int((vy - oy) / cell), int((vx - ox) / cell)
    def hm(i, j):
        i = min(max(i, 0), n - 1); j = min(max(j, 0), n - 1); return Hs[i, j]
    # point le plus haut du volcan (bord du cratere)
    best = (ci, cj)
    for di in range(-40, 41):
        for dj in range(-40, 41):
            if hm(ci + di, cj + dj) > hm(*best): best = (ci + di, cj + dj)
    bm = bmesh.new()
    rnd = random.Random(11)
    for k in range(7):
        a = k / 7 * math.tau + rnd.uniform(-0.3, 0.3)
        i, j = best[0] + math.sin(a) * 6, best[1] + math.cos(a) * 6
        pts = []
        for s_ in range(260):
            ii, jj = int(i), int(j)
            gi = hm(ii + 1, jj) - hm(ii - 1, jj); gj = hm(ii, jj + 1) - hm(ii, jj - 1)
            g = math.hypot(gi, gj) + 1e-6
            i -= gi / g * 0.6 + rnd.uniform(-0.15, 0.15); j -= gj / g * 0.6 + rnd.uniform(-0.15, 0.15)
            z = hm(int(i), int(j))
            if z < 40: break
            pts.append(Vector((ox + j * cell, oy + i * cell, z)))
        prev = None
        for idx, p in enumerate(pts):
            d = (pts[min(idx + 1, len(pts) - 1)] - pts[max(idx - 1, 0)]); d.z = 0
            if d.length < 1e-6: continue
            d.normalize(); side = Vector((-d.y, d.x, 0))
            wdt = 6 + 10 * (idx / max(1, len(pts))) + 3 * math.sin(idx * 0.3)
            row = [bm.verts.new(p + side * wdt * u + Vector((0, 0, 1.2 - 0.6 * abs(u)))) for u in (-1, -0.5, 0, 0.5, 1)]
            if prev:
                for jx in range(4): bm.faces.new((prev[jx], prev[jx + 1], row[jx + 1], row[jx]))
            prev = row
    # lac de lave dans le cratere
    bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=55,
                            matrix=Matrix.Translation((ox + best[1] * cell, oy + best[0] * cell, hm(*best) - 25)))
    me = bpy.data.meshes.new("lava"); bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new("lava", me)); ob.data.materials.append(bpy.data.materials.new("M_Lava"))
    export(ob, "SM_V2_LavaFlows")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--only", default="")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    only = set(x for x in a.only.split(",") if x)
    tex = textures()
    jobs = [
        ("Tree_Green_A", lambda: tree_asset("Tree_Green_A", 9, ["green"], 13, tex)),
        ("Tree_Green_B", lambda: tree_asset("Tree_Green_B", 21, ["green", "green", "autumn"], 15, tex)),
        ("Tree_Blossom_A", lambda: tree_asset("Tree_Blossom_A", 4, ["blossom", "blossom", "green"], 11, tex)),
        ("Tree_Autumn_A", lambda: tree_asset("Tree_Autumn_A", 33, ["autumn", "green"], 12, tex)),
        ("Pine_A", lambda: pine_asset("Pine_A", 3, 20, tex)),
        ("Pine_B", lambda: pine_asset("Pine_B", 17, 26, tex)),
        ("Dead_A", lambda: dead_asset("Dead_A", 301, 8)),
        ("Dead_B", lambda: dead_asset("Dead_B", 305, 10)),
        ("Grass_A", lambda: grass_asset("Grass_A", 7, "#2f4f17", "#a7bb52")),
        ("Grass_B", lambda: grass_asset("Grass_B", 20, "#2f4f17", "#a7bb52", dry=0.3)),
        ("Grass_Forest", lambda: grass_asset("Grass_Forest", 33, "#2f4a1c", "#86a43e", h=0.32)),
        ("Grass_Dune", lambda: grass_asset("Grass_Dune", 46, "#4e6a26", "#cfc684", h=0.5, dry=0.35)),
        ("Grass_Alpine", lambda: grass_asset("Grass_Alpine", 59, "#3b5222", "#a8b061", h=0.3, dry=0.25)),
        ("Flowers_Yellow", lambda: grass_asset("Flowers_Yellow", 50, "#2f4f17", "#a7bb52", "#f4d64a", blades=45)),
        ("Flowers_Pink", lambda: grass_asset("Flowers_Pink", 57, "#2f4f17", "#a7bb52", "#f2a0c6", blades=45)),
        ("Flowers_White", lambda: grass_asset("Flowers_White", 64, "#2f4f17", "#a7bb52", "#ffffff", blades=45)),
        ("Flowers_Blue", lambda: grass_asset("Flowers_Blue", 71, "#3b5222", "#a8b061", "#5a7cf2", h=0.3, blades=40)),
        ("Fern_A", lambda: fern_asset("Fern_A", 1, tex, 7, 0.9)),
        ("Fern_B", lambda: fern_asset("Fern_B", 2, tex, 9, 1.1)),
        ("Rock_Mossy", lambda: rock_asset("Rock_Mossy", 1.1, 1, "#5b5852", "#99938a", "#55702a")),
        ("Rock_Large", lambda: rock_asset("Rock_Large", 2.4, 2, "#5b5852", "#99938a", "#55702a")),
        ("Boulder", lambda: rock_asset("Boulder", 5.0, 3, "#4f4d48", "#9a968e", "#6a7a3a")),
        ("Cliff", lambda: rock_asset("Cliff", 9.0, 4, "#3e4048", "#6a6c72", None, flat=1.6)),
        ("Basalt_A", lambda: rock_asset("Basalt_A", 1.5, 5, "#0f0e0d", "#34302c")),
        ("Basalt_Pebble", lambda: rock_asset("Basalt_Pebble", 0.35, 6, "#0f0e0d", "#34302c", flat=0.7)),
        ("Rock_Shore", lambda: rock_asset("Rock_Shore", 2.0, 7, "#6b6359", "#b4aa98", "#7a8445")),
        ("LavaFlows", lava_flows),
    ]
    for name, fn in jobs:
        if only and name not in only:
            continue
        try:
            fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            print("[ECHEC] %s : %s" % (name, e), flush=True)


if __name__ == "__main__":
    main()
