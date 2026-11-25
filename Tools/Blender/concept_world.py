"""
AETHERWILD - Rendus de direction artistique de la carte (Cycles, jusqu'en 1440p).
Usage : python concept_world.py --scene prairie|foret|cimes|volcan|cote [--res preview|1440] [--samples N]
"""
import sys, os, math, random, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import bpy, bmesh
import numpy as np
from mathutils import Vector, Matrix, noise, Euler
from hero_common import hexc, link, paint, mix, sstep, apply_all

OUT = os.path.join(HERE, "..", "..", "Docs", "previews", "map")
NEEDLE_SCALE = 1.0
PENDING = []   # systemes de particules crees a la fin (sinon chaque ajout re-evalue des millions d'instances)
TMP = os.environ.get("AETHER_TMP", "/tmp")

# =============================================================== utilitaires materiaux
def nodes(m):
    m.use_nodes = True
    return m.node_tree.nodes, m.node_tree.links

def tex_leaf(path, palette, seed, kind="leaf"):
    """Texture RGBA de grappe de feuilles / petales / aiguilles (alpha decoupe)."""
    from PIL import Image, ImageDraw, ImageFilter
    rnd = random.Random(seed)
    S = 1024
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    n = {"leaf": 70, "petal": 120, "needle": 420, "fern": 1}[kind]
    if kind == "fern":
        # fronde : tige + folioles
        for side in (-1, 1):
            for i in range(26):
                t = i / 26; cx = S / 2 + side * 6; cy = S * 0.95 - t * S * 0.9
                L = (1 - t) ** 0.7 * S * 0.32; W = L * 0.18
                a = math.radians(-90 + side * (55 - 25 * t))
                pts = []
                for k in range(16):
                    u = k / 15 * math.tau
                    px, py = (math.cos(u) * 0.5 + 0.5) * L, math.sin(u) * W * (1 - 0.6 * math.cos(u))
                    pts.append((cx + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a)))
                c = palette[rnd.randrange(len(palette))]
                d.polygon(pts, fill=c + (255,))
        d.line([(S / 2, S * 0.97), (S / 2, S * 0.05)], fill=(60, 80, 30, 255), width=8)
    for k in range(n if kind != "fern" else 0):
        cx, cy = rnd.uniform(90, S - 90), rnd.uniform(90, S - 90)
        if kind == "needle":
            c = palette[rnd.randrange(len(palette))]
            if k % 6 == 0:   # amas de rameau
                d.ellipse([cx - 40, cy - 22, cx + 40, cy + 22], fill=tuple(int(x * 0.85) for x in c) + (255,))
            a = rnd.uniform(0, math.tau); L = rnd.uniform(50, 110)
            d.line([(cx, cy), (cx + math.cos(a) * L, cy + math.sin(a) * L)], fill=c + (255,), width=9)
            continue
        L = rnd.uniform(45, 95) * (0.55 if kind == "petal" else 1.0); W = L * (0.8 if kind == "petal" else 0.45)
        a = rnd.uniform(0, math.tau)
        pts = []
        for i in range(28):
            t = i / 28 * math.tau
            px, py = math.cos(t) * L, math.sin(t) * W * (1 - 0.35 * math.cos(t))
            pts.append((cx + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a)))
        c = palette[rnd.randrange(len(palette))]; v = rnd.uniform(0.75, 1.2)
        col = tuple(int(min(255, x * v)) for x in c)
        d.polygon(pts, fill=col + (255,))
        if kind == "leaf":   # nervure centrale
            d.line([(cx - math.cos(a) * L * 0.9, cy - math.sin(a) * L * 0.9), (cx + math.cos(a) * L * 0.9, cy + math.sin(a) * L * 0.9)],
                   fill=tuple(int(x * 0.7) for x in col) + (255,), width=3)
    im = im.filter(ImageFilter.SMOOTH)
    im.save(path)
    return path

def card_material(name, tex, transl=0.4, rough=0.5, hue_var=0.06):
    m = bpy.data.materials.new(name); N, L = nodes(m)
    b = N["Principled BSDF"]; b.inputs["Roughness"].default_value = rough
    img = N.new("ShaderNodeTexImage"); img.image = bpy.data.images.load(tex)
    oi = N.new("ShaderNodeObjectInfo")
    hsv = N.new("ShaderNodeHueSaturation")
    mr = N.new("ShaderNodeMapRange"); mr.inputs[3].default_value = 0.5 - hue_var; mr.inputs[4].default_value = 0.5 + hue_var
    L.new(oi.outputs["Random"], mr.inputs[0]); L.new(mr.outputs[0], hsv.inputs["Hue"])
    vr = N.new("ShaderNodeMapRange"); vr.inputs[3].default_value = 0.75; vr.inputs[4].default_value = 1.2
    L.new(oi.outputs["Random"], vr.inputs[0]); L.new(vr.outputs[0], hsv.inputs["Value"])
    L.new(img.outputs["Color"], hsv.inputs["Color"])
    L.new(hsv.outputs[0], b.inputs["Base Color"]); L.new(img.outputs["Alpha"], b.inputs["Alpha"])
    tr = N.new("ShaderNodeBsdfTranslucent"); L.new(hsv.outputs[0], tr.inputs["Color"])
    mx = N.new("ShaderNodeMixShader"); mx.inputs[0].default_value = transl
    tp = N.new("ShaderNodeBsdfTransparent"); mx2 = N.new("ShaderNodeMixShader")
    L.new(b.outputs[0], mx.inputs[1]); L.new(tr.outputs[0], mx.inputs[2])
    L.new(img.outputs["Alpha"], mx2.inputs[0]); L.new(tp.outputs[0], mx2.inputs[1]); L.new(mx.outputs[0], mx2.inputs[2])
    L.new(mx2.outputs[0], N["Material Output"].inputs["Surface"])
    return m

def vc_material(name, transl=0.3, rough=0.55, var=0.08):
    """Couleur de sommet + variation par instance + translucidite (herbes)."""
    m = bpy.data.materials.new(name); N, L = nodes(m)
    b = N["Principled BSDF"]; b.inputs["Roughness"].default_value = rough
    vc = N.new("ShaderNodeVertexColor"); vc.layer_name = "Col"
    oi = N.new("ShaderNodeObjectInfo"); hsv = N.new("ShaderNodeHueSaturation")
    mr = N.new("ShaderNodeMapRange"); mr.inputs[3].default_value = 0.5 - var * 0.5; mr.inputs[4].default_value = 0.5 + var * 0.5
    vr = N.new("ShaderNodeMapRange"); vr.inputs[3].default_value = 0.7; vr.inputs[4].default_value = 1.15
    L.new(oi.outputs["Random"], mr.inputs[0]); L.new(mr.outputs[0], hsv.inputs["Hue"])
    L.new(oi.outputs["Random"], vr.inputs[0]); L.new(vr.outputs[0], hsv.inputs["Value"])
    L.new(vc.outputs[0], hsv.inputs["Color"]); L.new(hsv.outputs[0], b.inputs["Base Color"])
    tr = N.new("ShaderNodeBsdfTranslucent"); L.new(hsv.outputs[0], tr.inputs["Color"])
    mx = N.new("ShaderNodeMixShader"); mx.inputs[0].default_value = transl
    L.new(b.outputs[0], mx.inputs[1]); L.new(tr.outputs[0], mx.inputs[2]); L.new(mx.outputs[0], N["Material Output"].inputs["Surface"])
    return m

def ground_material(name, palette):
    """Sol procedural : herbe/terre/roche/neige/sable selon pente et altitude, bruit multi-echelle + relief."""
    m = bpy.data.materials.new(name); N, L = nodes(m)
    b = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord"); geo = N.new("ShaderNodeNewGeometry")
    sepn = N.new("ShaderNodeSeparateXYZ"); L.new(geo.outputs["Normal"], sepn.inputs[0])
    sepp = N.new("ShaderNodeSeparateXYZ"); L.new(geo.outputs["Position"], sepp.inputs[0])
    def noise_tex(scale, detail=8):
        n = N.new("ShaderNodeTexNoise"); n.inputs["Scale"].default_value = scale; n.inputs["Detail"].default_value = detail
        L.new(tc.outputs["Object"], n.inputs["Vector"]); return n
    big, mid, fine = noise_tex(0.03), noise_tex(0.4), noise_tex(6.0)
    def ramp(inp, stops):
        r = N.new("ShaderNodeValToRGB"); cr = r.color_ramp
        cr.elements[0].position, cr.elements[0].color = stops[0]
        cr.elements[1].position, cr.elements[1].color = stops[-1]
        for p, c in stops[1:-1]:
            e = cr.elements.new(p); e.color = c
        L.new(inp, r.inputs[0]); return r
    base = ramp(big.outputs["Fac"], [(0.35, palette["a"]), (0.5, palette["b"]), (0.65, palette["c"])])
    # terre / sol nu en taches
    soil = ramp(mid.outputs["Fac"], [(0.58, (0, 0, 0, 1)), (0.66, (1, 1, 1, 1))])
    mx1 = N.new("ShaderNodeMix"); mx1.data_type = 'RGBA'; mx1.inputs[7].default_value = palette["soil"]
    L.new(soil.outputs["Color"], mx1.inputs["Factor"]); L.new(base.outputs["Color"], mx1.inputs[6])
    # roche selon pente
    rockr = ramp(fine.outputs["Fac"], [(0.3, palette["rock1"]), (0.7, palette["rock2"])])
    slope = N.new("ShaderNodeMapRange"); slope.inputs[1].default_value = palette.get("rock_from", 0.88); slope.inputs[2].default_value = palette.get("rock_to", 0.72)
    L.new(sepn.outputs[2], slope.inputs[0])
    mx2 = N.new("ShaderNodeMix"); mx2.data_type = 'RGBA'
    L.new(slope.outputs[0], mx2.inputs["Factor"]); L.new(mx1.outputs[2], mx2.inputs[6]); L.new(rockr.outputs["Color"], mx2.inputs[7])
    out = mx2
    if "snow" in palette:
        hs = N.new("ShaderNodeMapRange"); hs.inputs[1].default_value = palette["snow_from"]; hs.inputs[2].default_value = palette["snow_from"] + 25
        L.new(sepp.outputs[2], hs.inputs[0])
        flat = N.new("ShaderNodeMapRange"); flat.inputs[1].default_value = palette.get("snow_flat", (0.55, 0.8))[0]; flat.inputs[2].default_value = palette.get("snow_flat", (0.55, 0.8))[1]
        L.new(sepn.outputs[2], flat.inputs[0])
        mul = N.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'; L.new(hs.outputs[0], mul.inputs[0]); L.new(flat.outputs[0], mul.inputs[1])
        mx3 = N.new("ShaderNodeMix"); mx3.data_type = 'RGBA'; mx3.inputs[7].default_value = palette["snow"]
        L.new(mul.outputs[0], mx3.inputs["Factor"]); L.new(out.outputs[2], mx3.inputs[6]); out = mx3
    if "sand" in palette:
        hs = N.new("ShaderNodeMapRange"); hs.inputs[1].default_value = palette["sand_to"]; hs.inputs[2].default_value = palette["sand_to"] - 1.5
        L.new(sepp.outputs[2], hs.inputs[0])
        mx4 = N.new("ShaderNodeMix"); mx4.data_type = 'RGBA'; mx4.inputs[7].default_value = palette["sand"]
        L.new(hs.outputs[0], mx4.inputs["Factor"]); L.new(out.outputs[2], mx4.inputs[6]); out = mx4
    if "seabed" in palette:
        hs = N.new("ShaderNodeMapRange"); hs.inputs[1].default_value = -1.0; hs.inputs[2].default_value = -10.0
        L.new(sepp.outputs[2], hs.inputs[0])
        mx5 = N.new("ShaderNodeMix"); mx5.data_type = 'RGBA'; mx5.inputs[7].default_value = palette["seabed"]
        L.new(hs.outputs[0], mx5.inputs["Factor"]); L.new(out.outputs[2], mx5.inputs[6]); out = mx5
    L.new(out.outputs[2], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.92
    bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.6; bp.inputs["Distance"].default_value = 0.05
    L.new(fine.outputs["Fac"], bp.inputs["Height"]); L.new(bp.outputs[0], b.inputs["Normal"])
    return m

def rock_material(name, c1, c2, moss=None):
    m = bpy.data.materials.new(name); N, L = nodes(m)
    b = N["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.85
    tc = N.new("ShaderNodeTexCoord")
    vo = N.new("ShaderNodeTexVoronoi"); vo.inputs["Scale"].default_value = 1.5; L.new(tc.outputs["Object"], vo.inputs["Vector"])
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 4; nz.inputs["Detail"].default_value = 12
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    r = N.new("ShaderNodeValToRGB"); r.color_ramp.elements[0].color = c1; r.color_ramp.elements[1].color = c2
    L.new(nz.outputs["Fac"], r.inputs[0])
    col = r
    if moss:
        geo = N.new("ShaderNodeNewGeometry"); sep = N.new("ShaderNodeSeparateXYZ"); L.new(geo.outputs["Normal"], sep.inputs[0])
        mr = N.new("ShaderNodeMapRange"); mr.inputs[1].default_value = 0.55; mr.inputs[2].default_value = 0.85; L.new(sep.outputs[2], mr.inputs[0])
        mx = N.new("ShaderNodeMix"); mx.data_type = 'RGBA'; mx.inputs[7].default_value = moss
        L.new(mr.outputs[0], mx.inputs["Factor"]); L.new(r.outputs["Color"], mx.inputs[6]); col = mx
        L.new(mx.outputs[2], b.inputs["Base Color"])
    else:
        L.new(r.outputs["Color"], b.inputs["Base Color"])
    add = N.new("ShaderNodeMath"); add.operation = 'ADD'
    L.new(vo.outputs["Distance"], add.inputs[0]); L.new(nz.outputs["Fac"], add.inputs[1])
    bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.9; L.new(add.outputs[0], bp.inputs["Height"]); L.new(bp.outputs[0], b.inputs["Normal"])
    return m

def bark_material(name, color="#4e3526"):
    m = bpy.data.materials.new(name); N, L = nodes(m)
    b = N["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.85
    tc = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (6, 6, 0.8)
    L.new(tc.outputs["Object"], mp.inputs[0])
    vo = N.new("ShaderNodeTexVoronoi"); vo.inputs["Scale"].default_value = 12; L.new(mp.outputs[0], vo.inputs["Vector"])
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 40; L.new(mp.outputs[0], nz.inputs["Vector"])
    r = N.new("ShaderNodeValToRGB"); r.color_ramp.elements[0].color = tuple(c * 0.45 for c in hexc(color)[:3]) + (1,)
    r.color_ramp.elements[1].color = hexc(color); L.new(vo.outputs["Distance"], r.inputs[0]); L.new(r.outputs["Color"], b.inputs["Base Color"])
    bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 1.6
    add = N.new("ShaderNodeMath"); add.operation = 'ADD'; L.new(vo.outputs["Distance"], add.inputs[0]); L.new(nz.outputs["Fac"], add.inputs[1])
    L.new(add.outputs[0], bp.inputs["Height"]); L.new(bp.outputs[0], b.inputs["Normal"])
    return m

def emissive(name, color, strength):
    m = bpy.data.materials.new(name); N, L = nodes(m)
    b = N["Principled BSDF"]; b.inputs["Base Color"].default_value = color
    b.inputs["Emission Color"].default_value = color; b.inputs["Emission Strength"].default_value = strength
    return m

# =============================================================== geometrie
def terrain(name, fn, x0, x1, y0, y1, nx, ny, mat):
    xs = np.linspace(x0, x1, nx); ys = np.linspace(y0, y1, ny)
    verts = [(x, y, fn(x, y)) for y in ys for x in xs]
    idx = np.arange(nx * ny).reshape(ny, nx)
    faces = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1).tolist()
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    for p in me.polygons: p.use_smooth = True
    ob = link(bpy.data.objects.new(name, me)); ob.data.materials.append(mat)
    return ob

def weight_group(ob, name, wfn):
    vg = ob.vertex_groups.new(name=name)
    for v in ob.data.vertices:
        w = wfn(v.co)
        if w > 0.003: vg.add([v.index], min(1.0, w), 'REPLACE')

def grass_clump(name, seed, blades=70, h=0.45, base="#2f4f17", tip="#9fb64e", flowers=None, width=0.022, lean=0.25, dry=0.15):
    rnd = random.Random(seed)
    me = bpy.data.meshes.new(name); bm = bmesh.new(); cl = bm.loops.layers.color.new("Col")
    bc, tcol, dc = hexc(base), hexc(tip), hexc("#b9a35e")
    for k in range(blades):
        a = rnd.uniform(0, math.tau); r = rnd.uniform(0, 0.3) ** 0.7
        x0, y0 = math.cos(a) * r, math.sin(a) * r
        hh = h * rnd.uniform(0.5, 1.25); w = width * rnd.uniform(0.6, 1.4)
        lv = Vector((math.cos(a), math.sin(a), 0)) * rnd.uniform(0.05, lean)
        rot = rnd.uniform(0, math.tau); side = Vector((math.cos(rot), math.sin(rot), 0)) * w
        isdry = rnd.random() < dry
        rows = []
        for s in range(6):
            t = s / 5
            c = Vector((x0, y0, 0)) + lv * (t * t) * hh * 2.2 + Vector((0, 0, hh * t * (1 - 0.15 * t * t)))
            ww = side * (1 - t) ** 0.8 * (1 if t < 0.95 else 0.2)
            rows.append((bm.verts.new(c - ww), bm.verts.new(c + ww), t))
        for s in range(5):
            f = bm.faces.new((rows[s][0], rows[s][1], rows[s + 1][1], rows[s + 1][0]))
            for lp in f.loops:
                t = rows[s][2] if lp.vert in (rows[s][0], rows[s][1]) else rows[s + 1][2]
                c = mix(bc, dc if isdry else tcol, t ** 0.8)
                ao = 0.35 + 0.65 * t
                lp[cl] = (c[0] * ao, c[1] * ao, c[2] * ao, t)   # alpha = poids du vent (0 a la base)
    if flowers:
        fc = hexc(flowers)
        for k in range(rnd.randint(4, 9)):
            a = rnd.uniform(0, math.tau); r = rnd.uniform(0, 0.25)
            ctr = Vector((math.cos(a) * r, math.sin(a) * r, h * rnd.uniform(0.6, 1.15)))
            stem_b = bm.verts.new(ctr * Vector((1, 1, 0))); stem_t = bm.verts.new(ctr)
            for j in range(6):
                aa = math.tau * j / 6
                p1 = bm.verts.new(ctr + Vector((math.cos(aa) * 0.035, math.sin(aa) * 0.035, 0.008)))
                p2 = bm.verts.new(ctr + Vector((math.cos(aa + 0.5) * 0.035, math.sin(aa + 0.5) * 0.035, 0.008)))
                f = bm.faces.new((stem_t, p1, p2))
                for lp in f.loops: lp[cl] = fc
            cv = bm.verts.new(ctr + Vector((0, 0, 0.012)))
    bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(name, me))
    return ob

def collection_of(name, objs):
    """Collection d'instances : objets a l'origine, collection exclue du rendu direct."""
    coll = bpy.data.collections.new(name); bpy.context.scene.collection.children.link(coll)
    for o in objs:
        for c in o.users_collection: c.objects.unlink(o)
        coll.objects.link(o); o.location = (0, 0, 0)
    bpy.context.view_layer.layer_collection.children[coll.name].exclude = True
    return coll

def scatter(ob, coll, count, group, size=1.0, rnd=0.45, seed=0, align_normal=False):
    PENDING.append(lambda: _scatter(ob, coll, count, group, size, rnd, seed, align_normal))

def _scatter(ob, coll, count, group, size, rnd, seed, align_normal):
    ps = ob.modifiers.new(coll.name + str(seed), 'PARTICLE_SYSTEM').particle_system
    st = ps.settings; ps.seed = seed
    st.type = 'EMITTER'; st.count = count; st.frame_start = 1; st.frame_end = 1; st.lifetime = 9999
    st.emit_from = 'FACE'; st.distribution = 'RAND'; st.physics_type = 'NO'; st.use_emit_random = True
    st.render_type = 'COLLECTION'; st.instance_collection = coll; st.use_collection_pick_random = True
    st.particle_size = size; st.size_random = rnd
    st.use_rotations = True
    if align_normal:
        st.rotation_mode = 'NOR'; st.rotation_factor_random = 0.0
    else:
        st.rotation_mode = 'NONE'
    ps.vertex_group_density = group
    return ps

def rock(name, size, seed, mat, flat=0.8):
    rnd = random.Random(seed)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=size)
    ob = bpy.context.object; ob.name = name
    ob.scale = (rnd.uniform(0.8, 1.3), rnd.uniform(0.8, 1.2), flat); bpy.ops.object.transform_apply(scale=True)
    for i, (kind, st, sc) in enumerate((('VORONOI', 0.35, 0.9), ('CLOUDS', 0.12, 0.25), ('CLOUDS', 0.03, 0.06))):
        t = bpy.data.textures.new("rt%d" % i, kind); t.noise_scale = size * sc
        d = ob.modifiers.new("d%d" % i, 'DISPLACE'); d.texture = t; d.strength = size * st; d.texture_coords = 'LOCAL'
    apply_all(ob)
    ob.data.materials.append(mat)
    return ob

def broadleaf_tree(name, seed, leaf_mats, height=12.0, bark=None, leaves_per_blob=650, spread=1.0):
    rnd = random.Random(seed)
    nodes_, edges, radii = [(0, 0, -0.6), (0, 0, height * 0.26)], [(0, 1)], [0.75 * height / 12, 0.5 * height / 12]
    tips = []
    def branch(pi, d, L, r, depth):
        base = Vector(nodes_[pi]); mid = base + d * L * 0.5 + Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), 0)) * L * 0.08
        tip = base + d * L
        nodes_.extend([tuple(mid), tuple(tip)]); radii.extend([r * 1.1, r])
        edges.extend([(pi, len(nodes_) - 2), (len(nodes_) - 2, len(nodes_) - 1)]); ci = len(nodes_) - 1
        if depth <= 2:
            tips.append(tip)
        if depth == 0:
            return
        for k in range(3 if depth > 1 else 2):
            a = rnd.uniform(0, math.tau)
            nd = (d * 0.9 + Vector((math.cos(a), math.sin(a), 0)) * rnd.uniform(0.5, 0.9) * spread + Vector((0, 0, 0.45))).normalized()
            branch(ci, nd, L * rnd.uniform(0.6, 0.75), r * 0.6, depth - 1)
    for k in range(4):
        a = k * math.tau / 4 + rnd.uniform(-0.5, 0.5)
        branch(1, Vector((math.cos(a) * spread * 0.8, math.sin(a) * spread * 0.8, 1.0)).normalized(), height * 0.32, 0.3 * height / 12, 3)
    import generate_assets as ga
    trunk = ga.skin_object(name, nodes_, edges, radii, subdiv=2, branch=0.85)
    trunk.data.materials.append(bark or bark_material("bark"))
    objs = [trunk]
    for i, tp in enumerate(tips):
        em = blob_obj(name + "_crown", tp + Vector((0, 0, 0.2)), rnd.uniform(1.6, 2.4) * height / 12, (1.2, 1.2, 0.85))
        mat = leaf_mats[i % len(leaf_mats)]
        PENDING.append(lambda em=em, card=shared_card(mat), sd=seed * 31 + i, n=leaves_per_blob, k=height / 12: volume_cards(em, card, n, sd, k))
        em.parent = trunk
        objs.append(em)
    return trunk

CARD_CACHE = {}

def fern_obj(name, mat, seed, fronds=7, length=1.1):
    """Touffe de fougere : frondes arquees rayonnantes, UV sur la texture de fronde."""
    rnd = random.Random(seed)
    me = bpy.data.meshes.new(name); bm = bmesh.new(); uvl = bm.loops.layers.uv.new()
    for f in range(fronds):
        a = f / fronds * math.tau + rnd.uniform(-0.3, 0.3)
        L = length * rnd.uniform(0.7, 1.15); W = L * 0.32
        dirv = Vector((math.cos(a), math.sin(a), 0)); side = Vector((-math.sin(a), math.cos(a), 0))
        rows = []
        for i in range(7):
            t = i / 6
            c = dirv * L * t * 0.85 + Vector((0, 0, L * (0.75 * t - 0.65 * t * t)))
            rows.append((bm.verts.new(c - side * W / 2), bm.verts.new(c + side * W / 2), t))
        for i in range(6):
            fc = bm.faces.new((rows[i][0], rows[i][1], rows[i + 1][1], rows[i + 1][0]))
            uvs = [(0, rows[i][2]), (1, rows[i][2]), (1, rows[i + 1][2]), (0, rows[i + 1][2])]
            for lp, uv in zip(fc.loops, uvs): lp[uvl].uv = uv
    bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(name, me)); ob.data.materials.append(mat)
    return ob

def shared_card(mat):
    """Une seule carte par materiau, partagee par tous les arbres (taille ajustee par particule)."""
    if mat.name not in CARD_CACHE:
        CARD_CACHE[mat.name] = card_obj("card_" + mat.name, mat, 0.85)
    return CARD_CACHE[mat.name]

def blob_obj(name, loc, radius, scale=(1, 1, 1), kind="ico", r2=None, depth=None):
    """Volume emetteur cree via bmesh (sans bpy.ops : instantane meme avec des milliers d'objets)."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    if kind == "ico":
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=radius)
    else:
        bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=radius, radius2=r2, depth=depth)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    ob.location = loc; ob.scale = scale
    return ob

def card_obj(name, mat, size):
    me = bpy.data.meshes.new(name)
    s = size / 2
    me.from_pydata([(-s, 0, -s), (s, 0, -s), (s, 0, s), (-s, 0, s)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new();
    for i, l in enumerate(me.loops): uv.data[i].uv = [(0, 0), (1, 0), (1, 1), (0, 1)][l.vertex_index]
    ob = link(bpy.data.objects.new(name, me)); ob.data.materials.append(mat); ob.location = (0, 0, -5000)
    return ob

def volume_cards(em, card, count, seed, size=1.0):
    ps = em.modifiers.new("cards", 'PARTICLE_SYSTEM').particle_system; st = ps.settings; ps.seed = seed
    st.type = 'EMITTER'; st.count = count; st.frame_start = st.frame_end = 1; st.lifetime = 9999
    st.emit_from = 'VOLUME'; st.physics_type = 'NO'; st.render_type = 'OBJECT'; st.instance_object = card
    st.particle_size = size; st.size_random = 0.45; st.use_rotations = True; st.rotation_mode = 'NONE'; st.rotation_factor_random = 1.0
    em.show_instancer_for_render = False; em.show_instancer_for_viewport = False

def pine_tree(name, seed, needle_mat, height=16.0, bark=None):
    rnd = random.Random(seed)
    import generate_assets as ga
    trunk = ga.chain([(0, 0, -0.5), (0, 0, height * 0.5), (0, 0, height)], [0.38 * height / 16, 0.24 * height / 16, 0.03], name, subdiv=1)
    trunk.data.materials.append(bark or bark_material("barkpine", "#3e2c22"))
    # etages de branches : cones invisibles remplis de cartes d'aiguilles
    layers = 9
    for i in range(layers):
        t = i / layers
        z = height * (0.18 + 0.78 * t); r = (1 - t) ** 1.1 * height * 0.24 + 0.4
        r *= rnd.uniform(0.85, 1.15)
        em = blob_obj(name + "_tier", (rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3), z), r, kind="cone", r2=r * 0.3, depth=height * rnd.uniform(0.16, 0.22))
        em.parent = trunk
        PENDING.append(lambda em=em, card=shared_card(needle_mat), sd=seed + i, n=int(650 * (r + 1) * NEEDLE_SCALE): volume_cards(em, card, n, sd, 1.9))
    return trunk

def place(obj, loc, rot_z=0.0, scale=1.0):
    obj.location = loc; obj.rotation_euler = (0, 0, rot_z); obj.scale = (scale,) * 3

def water_plane(z, color="#0d3d4d", size=4000, wave=0.1, scale=0.6):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z)); w = bpy.context.object
    m = bpy.data.materials.new("water"); N, L = nodes(m); b = N["Principled BSDF"]
    b.inputs["Base Color"].default_value = hexc(color); b.inputs["Roughness"].default_value = 0.015
    b.inputs["Transmission Weight"].default_value = 0.9; b.inputs["IOR"].default_value = 1.333
    tc = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1, 2.5, 1)
    L.new(tc.outputs["Object"], mp.inputs[0])
    n1 = N.new("ShaderNodeTexNoise"); n1.inputs["Scale"].default_value = scale; n1.inputs["Detail"].default_value = 10
    L.new(mp.outputs[0], n1.inputs["Vector"])
    bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = wave; L.new(n1.outputs["Fac"], bp.inputs["Height"]); L.new(bp.outputs[0], b.inputs["Normal"])
    w.data.materials.append(m)
    # volume d'absorption sous la surface (profondeur teintee)
    vol = N.new("ShaderNodeVolumeAbsorption"); vol.inputs["Color"].default_value = hexc("#2a8a8a"); vol.inputs["Density"].default_value = 0.15
    return w

def sky(sun_dir=(-0.5, 0.85, 0.15), sun_energy=4.5, sun_color=(1.0, 0.85, 0.66), strength=1.0, haze=0.0003,
        haze_color=(0.82, 0.87, 0.96, 1), haze_height=600, **_):
    sc = bpy.context.scene
    d = Vector(sun_dir).normalized()
    elev = math.asin(max(0.01, d.z)); azim = math.atan2(d.x, d.y)
    w = bpy.data.worlds.new("sky"); w.use_nodes = True; sc.world = w
    sk = w.node_tree.nodes.new("ShaderNodeTexSky")
    try:
        sk.sun_elevation = elev; sk.sun_rotation = azim; sk.air_density = 1.2; sk.dust_density = 2.0
    except Exception: pass
    bg = w.node_tree.nodes["Background"]; bg.inputs[1].default_value = strength
    w.node_tree.links.new(sk.outputs[0], bg.inputs[0])
    sun = link(bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN')))
    sun.data.energy = sun_energy; sun.data.angle = math.radians(0.8); sun.data.color = sun_color
    sun.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    if haze > 0:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, haze_height / 2 - 20)); hz = bpy.context.object; hz.name = "haze"
        hz.scale = (8000, 8000, haze_height)
        hm = bpy.data.materials.new("haze"); N, L = nodes(hm); N.remove(N["Principled BSDF"])
        v = N.new("ShaderNodeVolumePrincipled"); v.inputs["Density"].default_value = haze; v.inputs["Color"].default_value = haze_color
        if "Anisotropy" in v.inputs: v.inputs["Anisotropy"].default_value = 0.7
        L.new(v.outputs[0], N["Material Output"].inputs["Volume"]); hz.data.materials.append(hm)
    return sun

def camera(loc, target, lens=28, focus=None, fstop=5.6):
    cam = link(bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))); cam.data.lens = lens; cam.data.clip_end = 20000
    cam.location = loc; cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if focus:
        cam.data.dof.use_dof = True; cam.data.dof.focus_distance = focus; cam.data.dof.aperture_fstop = fstop
    bpy.context.scene.camera = cam
    return cam

def render(path, res, samples, exposure):
    import time
    t0 = time.time()
    for fn in PENDING: fn()
    PENDING.clear()
    print("particules creees en %.0fs" % (time.time() - t0), flush=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = samples; sc.cycles.use_denoising = True
    sc.cycles.use_adaptive_sampling = True; sc.cycles.adaptive_threshold = 0.02
    sc.cycles.max_bounces = 5; sc.cycles.diffuse_bounces = 3; sc.cycles.glossy_bounces = 3; sc.cycles.transmission_bounces = 6
    sc.cycles.volume_bounces = 1; sc.cycles.transparent_max_bounces = 24
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = 'AgX'
    try: sc.view_settings.look = 'AgX - Punchy'
    except Exception: pass
    sc.view_settings.exposure = exposure
    sc.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)

# =============================================================== palettes vegetation
def vegetation_kit(prefix, base="#2f4f17", tip="#a7bb52", flowers=("#f4d64a", "#f2a0c6", "#ffffff", "#9b7cf0"), h=0.42, dry=0.15):
    g = [grass_clump("%s_g%d" % (prefix, k), 7 + k * 13, blades=80, h=h, base=base, tip=tip, dry=dry) for k in range(5)]
    f = [grass_clump("%s_f%d" % (prefix, k), 50 + k * 7, blades=45, h=h * 0.95, base=base, tip=tip, flowers=flowers[k % len(flowers)], dry=dry) for k in range(len(flowers) * 2)]
    gm = vc_material(prefix + "_grassmat")
    for o in g + f: o.data.materials.append(gm)
    return collection_of(prefix + "_grass", g), collection_of(prefix + "_flowers", f)

def leaf_mats(prefix):
    green = tex_leaf(os.path.join(TMP, "%s_leafG.png" % prefix), [(64, 112, 32), (88, 140, 42), (52, 92, 28), (110, 150, 50)], 1)
    autumn = tex_leaf(os.path.join(TMP, "%s_leafA.png" % prefix), [(196, 120, 40), (220, 160, 60), (170, 80, 30)], 3)
    blossom = tex_leaf(os.path.join(TMP, "%s_leafP.png" % prefix), [(250, 205, 222), (242, 175, 205), (255, 236, 244)], 2, kind="petal")
    needle = tex_leaf(os.path.join(TMP, "%s_needle.png" % prefix), [(30, 62, 34), (40, 78, 40), (26, 52, 30)], 4, kind="needle")
    fern = tex_leaf(os.path.join(TMP, "%s_fern.png" % prefix), [(60, 110, 40), (75, 125, 45)], 5, kind="fern")
    return {"green": card_material(prefix + "G", green), "autumn": card_material(prefix + "A", autumn),
            "blossom": card_material(prefix + "P", blossom, transl=0.5), "needle": card_material(prefix + "N", needle, transl=0.25),
            "fern": card_material(prefix + "F", fern, transl=0.45, rough=0.85)}

# =============================================================== scenes
def ridge(x, y, s, seed):
    return 1 - abs(noise.noise(Vector((x / s, y / s, seed))))

def scene_prairie(q):
    lm = leaf_mats("pr")
    gmat = ground_material("ground", {"a": hexc("#3d6a1c"), "b": hexc("#5b8426"), "c": hexc("#8a9a3a"), "soil": hexc("#5a4330"),
                                      "rock1": hexc("#3e4048"), "rock2": hexc("#6a6c72"), "rock_from": 0.9, "rock_to": 0.75,
                                      "snow": hexc("#eef3f8"), "snow_from": 260, "sand": hexc("#cbb68a"), "sand_to": 0.6})
    def h(x, y):
        z = 1.2 + 0.7 * noise.noise(Vector((x / 40, y / 40, 0.3))) + 0.2 * noise.noise(Vector((x / 8, y / 8, 1.7)))
        z -= 0.018 * max(0.0, y - 10)                                    # la prairie descend vers le lac
        shore = 85 + 12 * noise.noise(Vector((x / 35, 0.5, 2.0)))
        far = 330 + 20 * noise.noise(Vector((x / 50, 1.5, 3.0)))
        z -= sstep(shore - 5, shore + 12, y) * 3.0 * (1 - sstep(far - 20, far, y))
        z += sstep(far - 20, far + 60, y) * (6 + 14 * (noise.noise(Vector((x / 40, y / 40, 4))) * 0.5 + 0.5))
        if y > 900:
            r = ridge(x, y, 160, 5.0)
            z += sstep(900, 1500, y) * (120 + 420 * r ** 2.4) + 40 * noise.noise(Vector((x / 60, y / 60, 6))) * sstep(900, 1300, y)
        z += 2.5 * sstep(30, 140, abs(x - 10)) * sstep(80, 0, y)
        return z
    ter = terrain("ground", h, -1400, 1400, -40, 2200, 360, 380, gmat)
    near = lambda co: math.exp(-math.hypot(co.x - 3, co.y - 8) / 28) * (co.z > 0.25) * (co.y < 95)
    weight_group(ter, "grass", lambda co: near(co) + 0.015 * (co.y < 400) * (co.z > 0.3))
    weight_group(ter, "flowers", lambda co: near(co) * max(0.0, noise.noise(Vector((co.x / 6, co.y / 6, 7))) + 0.35))
    gc, fc = vegetation_kit("pr")
    scatter(ter, gc, q["grass"], "grass", seed=1)
    scatter(ter, fc, q["grass"] // 4, "flowers", seed=2, size=1.05)
    rm = rock_material("rock", hexc("#5b5852"), hexc("#99938a"), moss=hexc("#55702a"))
    rocks = [rock("r%d" % i, s_, i, rm) for i, s_ in enumerate((0.6, 1.1, 2.4, 0.4))]
    for (x, y, i, sc) in ((6.5, 9, 0, 1.0), (-4, 14, 3, 1.2), (12, 22, 1, 1.0), (-18, 30, 2, 1.0), (22, 60, 2, 1.6), (-35, 70, 1, 1.4)):
        r = rocks[i].copy(); link(r); place(r, (x, y, h(x, y) - 0.25), random.random() * 6, sc)
    for r_ in rocks: r_.location = (0, 0, -5000)
    rnd = random.Random(4)
    spots = [((-12, 24), [lm["blossom"], lm["blossom"], lm["green"]], 11), ((17, 40), [lm["green"]], 13),
             ((-32, 50), [lm["blossom"], lm["green"]], 10), ((38, 68), [lm["green"], lm["autumn"]], 14),
             ((-58, 78), [lm["green"]], 12), ((62, 36), [lm["blossom"]], 9), ((-80, 40), [lm["green"]], 15), ((85, 80), [lm["green"]], 13)]
    for k, ((x, y), mats, ht) in enumerate(spots):
        t = broadleaf_tree("tree%d" % k, 4 + k * 5, mats, height=ht, leaves_per_blob=q["leaves"])
        t.location = (x, y, h(x, y) - 0.3); t.rotation_euler = (0, 0, k * 1.3)
    k = 0
    for c in range(14):   # bosquets de l'autre rive
        cx = -560 + c * 80 + rnd.uniform(-25, 25); cy = 345 + rnd.uniform(0, 70)
        for j in range(rnd.randint(2, 5)):
            x = cx + rnd.uniform(-22, 22); y = cy + rnd.uniform(-15, 15); k += 1
            mats = [lm["green"], lm["autumn"]] if k % 6 == 0 else ([lm["blossom"], lm["green"]] if k % 9 == 0 else [lm["green"]])
            t = broadleaf_tree("far%d" % k, 100 + k, mats, height=rnd.uniform(11, 22), leaves_per_blob=q["leaves"] // 3)
            t.location = (x, y, h(x, y) - 0.5); t.rotation_euler = (0, 0, rnd.uniform(0, 6))
    water_plane(-0.15)
    import generate_assets as ga
    sh = ga.shrine("shrine"); sh.data.materials.append(rock_material("shrinestone", hexc("#8c877c"), hexc("#bdb6a8")))
    for p in sh.data.polygons:
        c = sum((sh.data.vertices[i].co for i in p.vertices), Vector()) / len(p.vertices)
        if c.z > 1.0 and abs(c.x) < 0.5 and abs(c.y) < 0.5: p.material_index = 1
    sh.data.materials.append(emissive("crystal", hexc("#7fe8ff"), 18)); place(sh, (-14, 74, h(-14, 74) - 0.2), 0.3, 1.3)
    l = link(bpy.data.objects.new("glow", bpy.data.lights.new("glow", 'POINT'))); l.data.energy = 5000; l.data.color = (0.45, 0.9, 1)
    l.location = (-14, 74, h(-14, 74) + 4)
    try:
        add_fox((3.0, 7.5, h(3.0, 7.5) + 0.02), math.radians(-30), 1.5)
    except Exception as e:
        print("renard ignore:", e)
    sky(sun_dir=(-0.62, 0.62, 0.48), sun_energy=4.2, haze=0.00012, haze_color=(0.75, 0.83, 0.97, 1), haze_height=900)
    camera((0.5, -3.0, max(3.4, h(0.5, -3.0) + 2.0)), (4, 120, 2), lens=26, focus=10.5, fstop=4.0)
    return -3.0

def add_fox(loc, rot, scale):
    """Construit Braisillon (hero_braisillon) dans la scene courante et le place."""
    import hero_braisillon as fox
    fox.reset = lambda: None            # ne pas vider la scene
    body, parts, nose, eyes = fox.assemble()
    root = link(bpy.data.objects.new("fox_root", None))
    for o in [*parts, nose, *eyes]:
        o.parent = root
    place(root, loc, rot, scale)

def scene_foret(q):
    lm = leaf_mats("fo")
    gmat = ground_material("ground", {"a": hexc("#33501a"), "b": hexc("#476a22"), "c": hexc("#5a5a26"), "soil": hexc("#3a2a1c"),
                                      "rock1": hexc("#4a4740"), "rock2": hexc("#6e6a60")})
    def h(x, y):
        return 0.8 * noise.noise(Vector((x / 25, y / 25, 0.3))) + 0.3 * noise.noise(Vector((x / 6, y / 6, 1.2))) + 0.15 * y * 0.02
    ter = terrain("ground", h, -160, 160, -20, 300, 220, 240, gmat)
    weight_group(ter, "grass", lambda co: math.exp(-math.hypot(co.x, co.y - 8) / 30) * (0.4 + max(0, noise.noise(Vector((co.x / 6, co.y / 6, 3))))))
    weight_group(ter, "fern", lambda co: math.exp(-math.hypot(co.x, co.y - 10) / 40))
    gc, fc = vegetation_kit("fo", base="#2f4a1c", tip="#86a43e", flowers=("#ffffff", "#c9b4ff"), h=0.32, dry=0.05)
    scatter(ter, gc, q["grass"] // 2, "grass", seed=1)
    ferns = [fern_obj("fern%d" % k, lm["fern"], k, fronds=6 + k, length=0.75 + 0.15 * k) for k in range(4)]
    fern_coll = collection_of("ferns", ferns)
    scatter(ter, fern_coll, q["grass"] // 10, "fern", seed=5, size=1.0, rnd=0.6)
    rm = rock_material("rock", hexc("#4b4a42"), hexc("#7d786c"), moss=hexc("#3f6a22"))
    for i, (x, y, s) in enumerate(((5, 12, 1.4), (-7, 18, 2.2), (14, 30, 3.0), (-3, 40, 1.0))):
        r = rock("r%d" % i, s, i + 7, rm); place(r, (x, y, h(x, y) - s * 0.3), i)
    rnd = random.Random(3)
    for k in range(int(q["trees"] * 1.8)):
        x = rnd.uniform(-45, 45); y = rnd.uniform(8, 130)
        if abs(x - 2) < 5: x += 10 * (1 if x >= 2 else -1)   # sentier central
        if rnd.random() < 0.45:
            t = pine_tree("p%d" % k, k, lm["needle"], height=rnd.uniform(18, 30))
        else:
            t = broadleaf_tree("b%d" % k, k, [lm["green"], lm["green"], lm["autumn"]], height=rnd.uniform(16, 24), leaves_per_blob=q["leaves"] // 2, spread=0.7)
        t.location = (x, y, h(x, y) - 0.4); t.rotation_euler = (0, 0, rnd.uniform(0, 6))
    sky(sun_dir=(-0.35, 0.55, 0.75), sun_energy=6.0, sun_color=(1.0, 0.88, 0.7), haze=0.0016, haze_color=(0.95, 0.93, 0.85, 1), haze_height=45)
    camera((2, -2, h(2, -2) + 1.7), (2, 60, h(2, 60) + 5), lens=24, focus=12, fstop=5.6)
    return -2.4

def scene_cimes(q):
    lm = leaf_mats("ci")
    gmat = ground_material("ground", {"a": hexc("#4f6a2a"), "b": hexc("#6e7d3a"), "c": hexc("#8f8f52"), "soil": hexc("#5c4e3e"),
                                      "rock1": hexc("#3c3d42"), "rock2": hexc("#77787c"), "rock_from": 0.86, "rock_to": 0.7,
                                      "snow": hexc("#f3f6fb"), "snow_from": 300, "snow_flat": (0.28, 0.5)})
    def h(x, y):
        z = 2.5 + 2.0 * noise.noise(Vector((x / 30, y / 30, 1))) + 0.025 * max(0.0, y)
        m, amp, f = 0.0, 1.0, 1 / 260.0
        for o in range(5):
            m += amp * (1 - abs(noise.noise(Vector((x * f, y * f, 8 + o))))) ** 2
            amp *= 0.5; f *= 2.1
        z += sstep(650, 1500, y) * m * 700
        return z
    ter = terrain("ground", h, -1500, 1500, -30, 2600, 420, 420, gmat)
    weight_group(ter, "grass", lambda co: math.exp(-math.hypot(co.x, co.y - 8) / 30) * (co.z < 30) + 0.01 * (co.z < 60))
    weight_group(ter, "flowers", lambda co: math.exp(-math.hypot(co.x, co.y - 8) / 22) * max(0, noise.noise(Vector((co.x / 5, co.y / 5, 9))) + 0.3))
    gc, fc = vegetation_kit("ci", base="#3b5222", tip="#a8b061", flowers=("#5a7cf2", "#f6f0ff", "#f4d64a", "#d94f8a"), h=0.32, dry=0.25)
    scatter(ter, gc, q["grass"], "grass", seed=1)
    scatter(ter, fc, q["grass"] // 4, "flowers", seed=2)
    rm = rock_material("rock", hexc("#4a4945"), hexc("#8e8a83"), moss=hexc("#6a7a3a"))
    for i, (x, y, s_) in enumerate(((7, 14, 1.5), (-12, 26, 3.5), (20, 45, 5.0), (-30, 60, 2.0))):
        r = rock("r%d" % i, s_, i + 21, rm); place(r, (x, y, h(x, y) - s_ * 0.3), i)
    rnd = random.Random(9)
    for k in range(q["trees"]):
        x = rnd.uniform(-220, 220); y = rnd.uniform(25, 200)
        if abs(x) < 22 and y < 90: continue
        t = pine_tree("p%d" % k, k, lm["needle"], height=rnd.uniform(14, 26)); t.location = (x, y, h(x, y) - 0.4)
    sky(sun_dir=(0.6, 0.35, 0.72), sun_energy=5.0, sun_color=(1.0, 0.9, 0.78), haze=0.00012, haze_color=(0.72, 0.82, 0.98, 1), haze_height=1500)
    camera((0, -4, h(0, -4) + 2.2), (10, 900, 140), lens=26, focus=14, fstop=8)
    return -3.1

def lava_material():
    m = bpy.data.materials.new("lava"); N, L = nodes(m); b = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    vo = N.new("ShaderNodeTexVoronoi"); vo.feature = 'DISTANCE_TO_EDGE'; vo.inputs["Scale"].default_value = 0.35
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 0.8; nz.inputs["Detail"].default_value = 6
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    mx = N.new("ShaderNodeMix"); mx.data_type = 'VECTOR'; mx.inputs["Factor"].default_value = 0.35
    L.new(tc.outputs["Object"], mx.inputs[4]); L.new(nz.outputs["Color"], mx.inputs[5]); L.new(mx.outputs[1], vo.inputs["Vector"])
    r = N.new("ShaderNodeValToRGB"); cr = r.color_ramp
    cr.elements[0].position = 0.0; cr.elements[0].color = (1.0, 0.55, 0.08, 1)
    cr.elements[1].position = 0.08; cr.elements[1].color = (0.012, 0.008, 0.006, 1)
    e = cr.elements.new(0.04); e.color = (0.9, 0.18, 0.02, 1)
    L.new(vo.outputs["Distance"], r.inputs[0])
    L.new(r.outputs["Color"], b.inputs["Base Color"]); L.new(r.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 9.0; b.inputs["Roughness"].default_value = 0.6
    return m

def ribbon(name, pts, widths, z_of, mat, lift=0.3):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); prev = None
    for i, (p, w) in enumerate(zip(pts, widths)):
        d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]); d.z = 0; d.normalize()
        side = Vector((-d.y, d.x, 0))
        row = []
        for u in (-1, -0.5, 0, 0.5, 1):
            q_ = p + side * w * u
            row.append(bm.verts.new((q_.x, q_.y, z_of(q_.x, q_.y) + lift - 0.15 * abs(u))))
        if prev:
            for j in range(4):
                bm.faces.new((prev[j], prev[j + 1], row[j + 1], row[j]))
        prev = row
    bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(name, me)); ob.data.materials.append(mat)
    for p_ in ob.data.polygons: p_.use_smooth = True
    return ob

def scene_volcan(q):
    gmat = ground_material("ground", {"a": hexc("#1b1918"), "b": hexc("#2a2523"), "c": hexc("#3a322d"), "soil": hexc("#4a2e22"),
                                      "rock1": hexc("#151312"), "rock2": hexc("#3a3532"), "rock_from": 0.9, "rock_to": 0.72})
    VC = Vector((150, 1900, 0))
    def h(x, y):
        z = 1.2 * noise.noise(Vector((x / 14, y / 14, 1))) + 4 * noise.noise(Vector((x / 60, y / 60, 2)))
        d = math.hypot(x - VC.x, y - VC.y)
        ang = math.atan2(y - VC.y, x - VC.x)
        cone = max(0.0, 1 - d / 1350) ** 1.6 * 900
        gully = (1 - abs(math.sin(ang * 22 + noise.noise(Vector((d / 90, 0, 3))) * 3))) ** 2 * 70 * sstep(1350, 250, d)
        crater = 160 * math.exp(-(d / 130) ** 2)
        return z + cone - gully - crater
    ter = terrain("ground", h, -1600, 1800, -30, 3600, 400, 420, gmat)
    lava = lava_material()
    rnd = random.Random(3)
    # riviere de lave qui traverse la plaine au premier plan
    pts, ws = [], []
    x = -180.0
    for i in range(90):
        y = 70 + 35 * math.sin(i * 0.11) + 12 * math.sin(i * 0.37)
        pts.append(Vector((x, y, 0))); ws.append(7 + 4 * math.sin(i * 0.23)); x += 4.5
    ribbon("lava_river", pts, ws, h, lava, lift=0.25)
    for k in range(6):   # coulees sur les flancs
        a0 = math.radians(-120 + k * 22 + rnd.uniform(-6, 6)); pts, ws = [], []
        for i in range(70):
            d = 140 + i * 16
            a = a0 + 0.12 * math.sin(i * 0.2 + k)
            pts.append(Vector((VC.x + math.cos(a) * d, VC.y + math.sin(a) * d, 0))); ws.append(6 + i * 0.12)
        ribbon("lava%d" % k, pts, ws, h, lava, lift=0.4)
    # lumieres le long de la riviere (eclaire le sol)
    for i in range(0, 90, 9):
        l = link(bpy.data.objects.new("lv%d" % i, bpy.data.lights.new("lv%d" % i, 'POINT')))
        l.data.energy = 60000; l.data.color = (1.0, 0.35, 0.08); l.data.shadow_soft_size = 6
        l.location = (pts and (-180 + i * 4.5), 70 + 35 * math.sin(i * 0.11), h(-180 + i * 4.5, 70) + 3)
    rm = rock_material("basalt", hexc("#0f0e0d"), hexc("#34302c"))
    for i in range(18):
        x = rnd.uniform(-60, 70); y = rnd.uniform(6, 60); s_ = rnd.uniform(0.5, 3.5)
        r = rock("r%d" % i, s_, i + 40, rm, flat=rnd.uniform(0.6, 1.2)); place(r, (x, y, h(x, y) - s_ * 0.3), i)
    # eboulis : des milliers de cailloux et blocs disperses pres de la camera
    pebbles = [rock("pb%d" % i, 0.25 + 0.2 * i, 90 + i, rm, flat=0.7) for i in range(4)]
    pcoll = collection_of("pebbles", pebbles)
    weight_group(ter, "pebbles", lambda co: math.exp(-math.hypot(co.x, co.y - 10) / 35) * (1 if co.y < 300 else 0))
    scatter(ter, pcoll, q["grass"] // 40, "pebbles", size=1.0, rnd=0.7, seed=7)
    dead = bark_material("deadwood", "#2b2522")
    for k in range(7):
        x = rnd.uniform(-80, 90); y = rnd.uniform(15, 140)
        t = broadleaf_tree("dead%d" % k, 300 + k, [dead], height=rnd.uniform(6, 10), leaves_per_blob=0, spread=1.2)
        t.location = (x, y, h(x, y) - 0.3); t.rotation_euler = (0, 0, rnd.uniform(0, 6))
    # panache de fumee + lueur du cratere
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(VC.x, VC.y, 1250)); sm = bpy.context.object; sm.scale = (380, 380, 650)
    mm = bpy.data.materials.new("smoke"); N, L = nodes(mm); N.remove(N["Principled BSDF"])
    v = N.new("ShaderNodeVolumePrincipled"); nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 7.0; nz.inputs["Detail"].default_value = 12
    tcs = N.new("ShaderNodeTexCoord"); L.new(tcs.outputs["Object"], nz.inputs["Vector"])
    mr = N.new("ShaderNodeMapRange"); mr.inputs[1].default_value = 0.5; mr.inputs[2].default_value = 0.68; mr.inputs[4].default_value = 0.025
    L.new(nz.outputs["Fac"], mr.inputs[0]); L.new(mr.outputs[0], v.inputs["Density"]); v.inputs["Color"].default_value = (0.2, 0.18, 0.17, 1)
    v.inputs["Color"].default_value = (0.09, 0.08, 0.08, 1)
    L.new(v.outputs[0], N["Material Output"].inputs["Volume"]); sm.data.materials.append(mm)
    glow = link(bpy.data.objects.new("crater", bpy.data.lights.new("crater", 'POINT'))); glow.data.energy = 3e7; glow.data.color = (1, 0.38, 0.08)
    glow.location = (VC.x, VC.y, 700); glow.data.shadow_soft_size = 60
    sky(sun_dir=(0.85, 0.5, 0.06), sun_energy=3.0, sun_color=(1.0, 0.55, 0.35), strength=0.5, haze=0.00014,
        haze_color=(0.85, 0.62, 0.52, 1), haze_height=1200)
    camera((-8, -10, h(-8, -10) + 3.5), (120, 1500, 260), lens=22, focus=40, fstop=11)
    return -2.7

def deep_water(z, size=6000, depth=80, color="#d8f6f4", absorb="#1d8fa8", density=0.16, wave=0.18, scale=0.3):
    """Eau volumique : turquoise sur les hauts-fonds, bleu profond au large."""
    me = bpy.data.meshes.new("sea"); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0); bm.to_mesh(me); bm.free()
    w = link(bpy.data.objects.new("sea", me)); w.scale = (size, size, depth); w.location = (0, 0, z - depth / 2)
    m = bpy.data.materials.new("sea"); N, L = nodes(m); b = N["Principled BSDF"]
    b.inputs["Base Color"].default_value = hexc(color); b.inputs["Roughness"].default_value = 0.02
    b.inputs["Transmission Weight"].default_value = 1.0; b.inputs["IOR"].default_value = 1.333
    tc = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (size * scale, size * scale * 2.5, 1)
    L.new(tc.outputs["Generated"], mp.inputs[0])
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Detail"].default_value = 10; L.new(mp.outputs[0], nz.inputs["Vector"])
    bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = wave; L.new(nz.outputs["Fac"], bp.inputs["Height"]); L.new(bp.outputs[0], b.inputs["Normal"])
    ab = N.new("ShaderNodeVolumePrincipled")
    ab.inputs["Color"].default_value = (0.12, 0.5, 0.62, 1)          # diffusion bleutee
    ab.inputs["Density"].default_value = density * 0.35
    ab.inputs["Absorption Color"].default_value = hexc(absorb)
    L.new(ab.outputs[0], N["Material Output"].inputs["Volume"])
    w.data.materials.append(m)
    return w

def clouds(n, seed, zmin=500, zmax=1200, center=(0, 2500), spread=3000):
    rnd = random.Random(seed)
    m = bpy.data.materials.new("cloud"); N, L = nodes(m); N.remove(N["Principled BSDF"])
    v = N.new("ShaderNodeVolumePrincipled"); v.inputs["Color"].default_value = (1, 1, 1, 1)
    tc = N.new("ShaderNodeTexCoord"); nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 3; nz.inputs["Detail"].default_value = 8
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    gr = N.new("ShaderNodeVectorMath"); gr.operation = 'LENGTH'; L.new(tc.outputs["Object"], gr.inputs[0])
    sub = N.new("ShaderNodeMath"); sub.operation = 'SUBTRACT'; L.new(nz.outputs["Fac"], sub.inputs[0]); L.new(gr.outputs["Value"], sub.inputs[1])
    mr = N.new("ShaderNodeMapRange"); mr.inputs[1].default_value = -0.35; mr.inputs[2].default_value = 0.0; mr.inputs[4].default_value = 0.05
    L.new(sub.outputs[0], mr.inputs[0]); L.new(mr.outputs[0], v.inputs["Density"])
    L.new(v.outputs[0], N["Material Output"].inputs["Volume"])
    for i in range(n):
        cx = center[0] + rnd.uniform(-spread, spread); cy = center[1] + rnd.uniform(-spread * 0.4, spread); cz = rnd.uniform(zmin, zmax)
        R = rnd.uniform(120, 260)
        for j in range(rnd.randint(4, 7)):     # cumulus : plusieurs boules qui se chevauchent
            me = bpy.data.meshes.new("c%d_%d" % (i, j)); bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0); bm.to_mesh(me); bm.free()
            o = link(bpy.data.objects.new("cloud%d_%d" % (i, j), me)); o.data.materials.append(m)
            r = R * rnd.uniform(0.55, 1.0)
            o.location = (cx + rnd.uniform(-1.6, 1.6) * R, cy + rnd.uniform(-0.8, 0.8) * R, cz + rnd.uniform(0, 0.7) * R)
            o.scale = (r, r * rnd.uniform(0.8, 1.1), r * rnd.uniform(0.75, 0.95))

def scene_cote(q):
    lm = leaf_mats("co")
    gmat = ground_material("ground", {"a": hexc("#5a7f2a"), "b": hexc("#7f9c3c"), "c": hexc("#a7a95a"), "soil": hexc("#7a6a4c"),
                                      "rock1": hexc("#6a6258"), "rock2": hexc("#b2a896"), "rock_from": 0.8, "rock_to": 0.62,
                                      "sand": hexc("#e8d7a8"), "sand_to": 3.0, "seabed": hexc("#1d3c3e")})
    def edge(x):
        return 30 + 7 * math.sin(x / 35) + 110 * sstep(50, 200, x) + 60 * sstep(-120, -260, x)
    def h(x, y):
        plateau = 18 + 1.5 * noise.noise(Vector((x / 25, y / 25, 1))) + 25 * sstep(-140, -300, x)
        ye = edge(x)
        beach = 2.2 - max(0.0, y - ye - 8) * 0.07 - sstep(ye + 25, ye + 160, y) * 45 + 0.4 * noise.noise(Vector((x / 10, y / 10, 2)))
        t = sstep(ye - 2, ye + 7, y)
        cliffnoise = 2.0 * noise.noise(Vector((x / 6, y / 6, 4))) * t * (1 - t) * 4
        return plateau * (1 - t) + beach * t + cliffnoise
    ter = terrain("ground", h, -900, 900, -40, 1500, 380, 360, gmat)
    weight_group(ter, "grass", lambda co: math.exp(-math.hypot(co.x + 4, co.y - 24) / 18) * (co.z > 12))
    weight_group(ter, "flowers", lambda co: math.exp(-math.hypot(co.x + 4, co.y - 24) / 14) * (co.z > 12) * max(0, noise.noise(Vector((co.x / 5, co.y / 5, 2))) + 0.25))
    gc, fc = vegetation_kit("co", base="#4e6a26", tip="#cfc684", flowers=("#ffffff", "#f4d64a", "#f0a0c8"), h=0.5, dry=0.35)
    scatter(ter, gc, q["grass"], "grass", seed=1)
    scatter(ter, fc, q["grass"] // 5, "flowers", seed=2)
    rm = rock_material("rock", hexc("#6b6359"), hexc("#b4aa98"), moss=hexc("#7a8445"))
    rnd = random.Random(5)
    for i in range(14):
        x = rnd.uniform(-120, 160); ye = edge(x); y = ye + rnd.uniform(2, 40); s_ = rnd.uniform(1, 5)
        r = rock("r%d" % i, s_, i + 60, rm, flat=rnd.uniform(0.6, 1.1)); place(r, (x, y, h(x, y) - s_ * 0.3), i)
    for k, (x, y) in enumerate(((-22, 6), (26, 14), (-40, 16))):
        t = broadleaf_tree("t%d" % k, k + 5, [lm["green"]], height=rnd.uniform(8, 11), leaves_per_blob=q["leaves"] // 2, spread=1.3)
        t.location = (x, y, h(x, y) - 0.3); t.rotation_euler = (math.radians(6), 0, rnd.uniform(0, 6))
    deep_water(0.0)
    clouds(10, 4)
    sky(sun_dir=(0.55, 0.7, 0.32), sun_energy=4.5, sun_color=(1.0, 0.86, 0.68), haze=0.00007, haze_color=(0.75, 0.85, 1.0, 1), haze_height=800)
    camera((-4, 27, h(-4, 27) + 2.0), (70, 110, -6), lens=20, focus=8, fstop=8)
    return -3.0

def scene_ile(q):
    """Vue aerienne de l'ile entiere, a partir du VRAI relief du jeu (Art/Terrain + world.json)."""
    import json
    from PIL import Image
    from scipy import ndimage
    ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
    w = json.load(open(os.path.join(ROOT, "Content", "Data", "world.json")))
    Lc = w["landscape"]
    Hm = np.array(Image.open(os.path.join(ROOT, Lc["heightmap"]))).astype(np.float32) / 65535 * 1024 - 80
    N = 1009 if q["grass"] > 200000 else 505
    H = ndimage.zoom(Hm, N / Hm.shape[0], order=1)[:N, :N]
    size = (Lc["resolution"] - 1) * Lc["scale"][0] / 100.0
    half = size / 2
    xs = np.linspace(-half, half, N)
    gmat = ground_material("ground", {"a": hexc("#3f6b1d"), "b": hexc("#5d8628"), "c": hexc("#8d9b3d"), "soil": hexc("#5a4330"),
                                      "rock1": hexc("#4a4744"), "rock2": hexc("#7e7a74"), "rock_from": 0.93, "rock_to": 0.8,
                                      "snow": hexc("#f2f5fa"), "snow_from": 560, "snow_flat": (0.45, 0.7),
                                      "sand": hexc("#d8c596"), "sand_to": 2.5, "seabed": hexc("#16383c")})
    verts = [(xs[j], xs[i], float(H[i, j])) for i in range(N) for j in range(N)]
    idx = np.arange(N * N).reshape(N, N)
    faces = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1).tolist()
    me = bpy.data.meshes.new("ile"); me.from_pydata(verts, [], faces); me.update()
    for p_ in me.polygons: p_.use_smooth = True
    ter = link(bpy.data.objects.new("ile", me)); ter.data.materials.append(gmat)
    vx, vy = w["volcano"][0] / 100.0, w["volcano"][1] / 100.0
    # cendres autour du volcan (couleur par sommets melangee au materiau via un 2e materiau ? -> zones sombres via vertex group de scatter)
    def forest_w(co):
        f = 0.5 + 0.75 * noise.noise(Vector((co.x / 280.0, co.y / 280.0, 2.0))) + 0.25 * noise.noise(Vector((co.x / 75.0, co.y / 75.0, 5.0)))
        vd = math.hypot(co.x - vx, co.y - vy)
        return sstep(0.5, 0.75, f) * (co.z > 3) * (vd > 1300)
    weight_group(ter, "broad", lambda co: forest_w(co) * (co.z < 320) * (co.normal.z if hasattr(co, "normal") else 1))
    weight_group(ter, "pine", lambda co: (sstep(0.3, 0.6, 0.5 + 0.75 * noise.noise(Vector((co.x / 280.0, co.y / 280.0, 2.0))))) * (140 < co.z < 620) * (math.hypot(co.x - vx, co.y - vy) > 1300))
    weight_group(ter, "ash", lambda co: (math.hypot(co.x - vx, co.y - vy) < 1350) * (co.z > 30))
    # arbres simplifies (lisibles a 8 km) : houppiers et sapins
    def blob_tree(name, col, r=4.5, h=9.0, cone=False):
        me = bpy.data.meshes.new(name); bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.5, radius2=0.3, depth=h * 0.5, matrix=Matrix.Translation((0, 0, h * 0.25)))
        if cone:
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r, radius2=0.2, depth=h, matrix=Matrix.Translation((0, 0, h * 0.75)))
        else:
            bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r, matrix=Matrix.Translation((0, 0, h * 0.8)))
        bm.to_mesh(me); bm.free()
        ob = link(bpy.data.objects.new(name, me))
        m = bpy.data.materials.new(name + "_m"); Nn, Ll = nodes(m); b = Nn["Principled BSDF"]
        oi = Nn.new("ShaderNodeObjectInfo"); r_ = Nn.new("ShaderNodeValToRGB")
        r_.color_ramp.elements[0].color = tuple(c * 0.7 for c in col[:3]) + (1,); r_.color_ramp.elements[1].color = tuple(min(1, c * 1.25) for c in col[:3]) + (1,)
        Ll.new(oi.outputs["Random"], r_.inputs[0]); Ll.new(r_.outputs["Color"], b.inputs["Base Color"]); b.inputs["Roughness"].default_value = 0.85
        ob.data.materials.append(m)
        return ob
    broad = [blob_tree("bt%d" % k, c) for k, c in enumerate((hexc("#2f5a1c"), hexc("#3a6a22"), hexc("#6e7a2a"), hexc("#a8692a")))]
    pines = [blob_tree("pt%d" % k, c, r=3.2, h=16, cone=True) for k, c in enumerate((hexc("#1f3d22"), hexc("#28492a")))]
    rocks = [rock("ash%d" % k, 6 + 4 * k, 200 + k, rock_material("ashm%d" % k, hexc("#141210"), hexc("#3a332e")), flat=0.6) for k in range(2)]
    scatter(ter, collection_of("broad_c", broad), q["trees"] * 2500, "broad", size=1.0, rnd=0.5, seed=11)
    scatter(ter, collection_of("pine_c", pines), q["trees"] * 1500, "pine", size=1.0, rnd=0.4, seed=12)
    scatter(ter, collection_of("ash_c", rocks), q["trees"] * 150, "ash", size=1.0, rnd=0.6, seed=13)
    # coulees de lave (meme trace que l'export Unreal) + fumee
    lava = lava_material()
    try:
        bm = bmesh.new()
        n = H.shape[0]; cell = size / (n - 1)
        def hm(i, j):
            return float(H[min(max(int(i), 0), n - 1), min(max(int(j), 0), n - 1)])
        ci, cj = int((vy + half) / cell), int((vx + half) / cell)
        best = max(((ci + di, cj + dj) for di in range(-25, 26) for dj in range(-25, 26)), key=lambda t: hm(*t))
        rnd = random.Random(11)
        for k in range(7):
            a = k / 7 * math.tau + rnd.uniform(-0.3, 0.3)
            i, j = best[0] + math.sin(a) * 4, best[1] + math.cos(a) * 4; pts = []
            for st in range(500):
                gi = hm(i + 1, j) - hm(i - 1, j); gj = hm(i, j + 1) - hm(i, j - 1); g = math.hypot(gi, gj) + 1e-6
                i -= gi / g * 0.5 + rnd.uniform(-0.12, 0.12); j -= gj / g * 0.5 + rnd.uniform(-0.12, 0.12)
                z = hm(i, j)
                if z < 40: break
                pts.append(Vector((-half + j * cell, -half + i * cell, z)))
            prev = None
            for t_, p_ in enumerate(pts):
                d = pts[min(t_ + 1, len(pts) - 1)] - pts[max(t_ - 1, 0)]; d.z = 0
                if d.length < 1e-6: continue
                d.normalize(); sd = Vector((-d.y, d.x, 0)); wd = 10 + 14 * t_ / max(1, len(pts))
                row = [bm.verts.new(p_ + sd * wd * u + Vector((0, 0, 3))) for u in (-1, 0, 1)]
                if prev:
                    for jx in range(2): bm.faces.new((prev[jx], prev[jx + 1], row[jx + 1], row[jx]))
                prev = row
        me2 = bpy.data.meshes.new("lava"); bm.to_mesh(me2); bm.free()
        lo = link(bpy.data.objects.new("lava", me2)); lo.data.materials.append(lava)
        cz = hm(*best)
    except Exception as e:
        print("lave ignoree:", e); cz = 600
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(vx, vy, cz + 700)); sm = bpy.context.object; sm.scale = (420, 420, 800)
    mm = bpy.data.materials.new("smoke"); Nn, Ll = nodes(mm); Nn.remove(Nn["Principled BSDF"])
    v = Nn.new("ShaderNodeVolumePrincipled"); nz = Nn.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 6; nz.inputs["Detail"].default_value = 10
    tcs = Nn.new("ShaderNodeTexCoord"); Ll.new(tcs.outputs["Object"], nz.inputs["Vector"])
    mr = Nn.new("ShaderNodeMapRange"); mr.inputs[1].default_value = 0.5; mr.inputs[2].default_value = 0.68; mr.inputs[4].default_value = 0.01
    Ll.new(nz.outputs["Fac"], mr.inputs[0]); Ll.new(mr.outputs[0], v.inputs["Density"]); v.inputs["Color"].default_value = (0.12, 0.11, 0.1, 1)
    Ll.new(v.outputs[0], Nn["Material Output"].inputs["Volume"]); sm.data.materials.append(mm)
    deep_water(0.0, size=40000, depth=120)
    clouds(16, 9, zmin=1400, zmax=2200, center=(0, 0), spread=6000)
    sky(sun_dir=(-0.5, -0.45, 0.45), sun_energy=4.5, sun_color=(1.0, 0.9, 0.78), haze=0.00004, haze_color=(0.72, 0.82, 0.98, 1), haze_height=4000)
    cam = camera((700, 7600, 3300), (-100, 300, 0), lens=30)
    cam.data.clip_end = 60000
    return -3.2

SCENES = {"ile": scene_ile, "prairie": scene_prairie, "foret": scene_foret, "cimes": scene_cimes, "volcan": scene_volcan, "cote": scene_cote}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="prairie"); ap.add_argument("--res", default="preview"); ap.add_argument("--samples", type=int, default=0)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    preview = a.res == "preview"
    q = {"grass": 150000 if preview else 450000, "leaves": 500 if preview else 700, "trees": 40 if preview else 70, "needles": 1.0 if preview else 0.6}
    NEEDLE_SCALE = q["needles"]
    reset()
    import time; t0 = time.time()
    exposure = SCENES[a.scene](q)
    print("scene construite en %.0fs (%d objets)" % (time.time() - t0, len(bpy.data.objects)), flush=True)
    res = (960, 540) if preview else (2560, 1440)
    render(os.path.join(OUT, "%s%s.png" % (a.scene, "_preview" if preview else "_1440p")), res, a.samples or (24 if preview else 48), exposure)
