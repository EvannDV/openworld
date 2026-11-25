"""
AETHERWILD - Generateur procedural d'assets (Blender 4.2+ / 5.x)
=================================================================
Genere toutes les creatures (mesh + squelette + animations), le dresseur,
et les assets d'environnement (rochers, arbres, herbe, fleurs, sanctuaire),
puis les exporte en FBX prets pour Unreal Engine 5.

Utilisation :
    blender -b -P generate_assets.py -- --out ../../Art --previews ../../Docs/previews
    (ou avec le module Python bpy :  python generate_assets.py --out ... )

Options :
    --only braisillon,galetor   ne genere que ces assets
    --no-render                 pas d'images de previsualisation

Convention : 1 unite Blender = 1 metre, les creatures regardent vers -Y
(meme convention que le Mannequin UE -> yaw -90 dans Unreal).
Couleurs : attribut de couleur "Col" (RGB = albedo, Alpha = masque emissif
pour les creatures / poids du vent pour la vegetation).
"""
import bpy
import math
import os
import random
import sys
import argparse
import zlib

import numpy as np
from mathutils import Vector, Matrix, Quaternion, noise

TAU = math.tau

# ---------------------------------------------------------------------------
# Utilitaires generaux
# ---------------------------------------------------------------------------

def hexcol(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smoothstep(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0 + 1e-9))
    return t * t * (3 - 2 * t)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 30
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0


def link(ob):
    bpy.context.scene.collection.objects.link(ob)


def apply_mods(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def skin_object(name, nodes, edges, radii, subdiv=2, branch=0.5, scale=None):
    """Cree une forme organique a partir d'un graphe de points + rayons (Skin modifier)."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([Vector(n) for n in nodes], edges, [])
    me.update()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    mod = ob.modifiers.new("Skin", 'SKIN')
    mod.branch_smoothing = branch
    mod.use_smooth_shade = True
    sv = me.skin_vertices[0].data
    for i, r in enumerate(radii):
        rr = r if isinstance(r, (tuple, list)) else (r, r)
        sv[i].radius = rr
        sv[i].use_root = (i == 0)
    if subdiv:
        sd = ob.modifiers.new("Subd", 'SUBSURF')
        sd.levels = subdiv
        sd.render_levels = subdiv
    apply_mods(ob)
    if scale is not None:
        ob.data.transform(Matrix.Diagonal((*scale, 1.0)))
    return ob


def chain(points, radii, name="chain", subdiv=2, scale=None):
    edges = [(i, i + 1) for i in range(len(points) - 1)]
    return skin_object(name, points, edges, radii, subdiv=subdiv, scale=scale)


def uv_sphere(name, center, radius, seg=16, rings=10, scale=(1, 1, 1)):
    me = bpy.data.meshes.new(name)
    verts, faces = [], []
    for r in range(rings + 1):
        th = math.pi * r / rings
        for s in range(seg):
            ph = TAU * s / seg
            verts.append((radius * math.sin(th) * math.cos(ph) * scale[0],
                          radius * math.sin(th) * math.sin(ph) * scale[1],
                          radius * math.cos(th) * scale[2]))
    for r in range(rings):
        for s in range(seg):
            a = r * seg + s
            b = r * seg + (s + 1) % seg
            faces.append((a, b, b + seg, a + seg))
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    ob.data.transform(Matrix.Translation(Vector(center)))
    for p in me.polygons:
        p.use_smooth = True
    # fusionne les poles
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(me)
    bm.free()
    return ob


def paint(ob, fn):
    """fn(co, normal) -> (r, g, b, a) en sRGB."""
    me = ob.data
    attr = me.color_attributes.get("Col") or me.color_attributes.new("Col", 'BYTE_COLOR', 'CORNER')
    vcols = [fn(v.co, v.normal) for v in me.vertices]
    for li, loop in enumerate(me.loops):
        attr.data[li].color_srgb = vcols[loop.vertex_index]
    return ob


def solid_paint(ob, rgb, alpha=0.0, jitter=0.06, freq=6.0, seed=0.0):
    def fn(co, n):
        v = 1.0 + jitter * noise.noise(co * freq + Vector((seed, seed, seed)))
        return (clamp(rgb[0] * v), clamp(rgb[1] * v), clamp(rgb[2] * v), alpha)
    return paint(ob, fn)


def set_group(ob, bone, w=1.0):
    vg = ob.vertex_groups.get(bone) or ob.vertex_groups.new(name=bone)
    vg.add(list(range(len(ob.data.vertices))), w, 'REPLACE')


def auto_weights(ob, bones, allowed=None, top=3, falloff=4.0):
    """Poids de skinning par distance aux segments d'os (robuste, deterministe)."""
    segs = [(b[0], np.array(b[1]), np.array(b[2])) for b in bones
            if (allowed is None or b[0] in allowed) and b[0] not in ('root', 'saddle')]
    if not segs:
        return
    V = np.array([v.co[:] for v in ob.data.vertices])
    D = np.zeros((len(V), len(segs)))
    for j, (_, h, t) in enumerate(segs):
        ab = t - h
        l2 = max(float(ab @ ab), 1e-9)
        tt = np.clip(((V - h) @ ab) / l2, 0, 1)
        P = h + tt[:, None] * ab
        D[:, j] = np.linalg.norm(V - P, axis=1)
    W = 1.0 / (D + 0.01) ** falloff
    idx = np.argsort(-W, axis=1)[:, :top]
    groups = {}
    for j, (name, _, _) in enumerate(segs):
        groups[j] = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
    for i in range(len(V)):
        ws = W[i, idx[i]]
        ws = ws / ws.sum()
        for k, j in enumerate(idx[i]):
            if ws[k] > 0.01:
                groups[j].add([i], float(ws[k]), 'REPLACE')


def join(objs, name):
    objs = [o for o in objs if o is not None]
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    return ob


def build_armature(bones):
    arm = bpy.data.armatures.new("ArmatureData")
    ob = bpy.data.objects.new("Armature", arm)   # "Armature" : UE ignore ce noeud racine
    link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    eb = {}
    for name, h, t, parent in bones:
        b = arm.edit_bones.new(name)
        b.head = Vector(h)
        b.tail = Vector(t)
        if (b.tail - b.head).length < 1e-3:
            b.tail = b.head + Vector((0, 0, 0.05))
        b.roll = 0.0
        if parent:
            b.parent = eb[parent]
        eb[name] = b
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def make_action(arm_ob, name, frames, fn):
    """fn(t in [0,1]) -> dict bone -> {'r': [(axe_monde, angle)...], 'l': vec_monde, 's': scale}"""
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    if arm_ob.animation_data is None:
        arm_ob.animation_data_create()
    arm_ob.animation_data.action = act
    pbs = arm_ob.pose.bones
    rest = {pb.name: pb.bone.matrix_local.to_3x3().inverted() for pb in pbs}
    for pb in pbs:
        pb.rotation_mode = 'QUATERNION'
    for f in range(frames + 1):
        t = f / frames
        pose = fn(t)
        for pb in pbs:
            d = pose.get(pb.name, {})
            minv = rest[pb.name]
            q = Quaternion()
            for axis, ang in d.get('r', []):
                la = (minv @ Vector(axis)).normalized()
                q = q @ Quaternion(la, ang)
            pb.rotation_quaternion = q
            pb.location = minv @ Vector(d.get('l', (0, 0, 0)))
            s = d.get('s', 1.0)
            pb.scale = (s, s, s) if not isinstance(s, (tuple, list)) else s
            pb.keyframe_insert("rotation_quaternion", frame=f + 1)
            pb.keyframe_insert("location", frame=f + 1)
            pb.keyframe_insert("scale", frame=f + 1)
    act.use_frame_range = True
    act.frame_start = 1
    act.frame_end = frames + 1
    return act


def P(d, bone, r=None, l=None, s=None):
    e = d.setdefault(bone, {})
    if r:
        e.setdefault('r', []).extend(r)
    if l is not None:
        e['l'] = tuple(a + b for a, b in zip(e.get('l', (0, 0, 0)), l))
    if s is not None:
        e['s'] = s


X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)

# ---------------------------------------------------------------------------
# Peinture des corps
# ---------------------------------------------------------------------------

def body_painter(spec, height_ref):
    p, s, a = hexcol(spec['primary']), hexcol(spec['secondary']), hexcol(spec['accent'])
    pattern = spec.get('pattern', 'none')
    glow = spec.get('pattern_glow', 0.0)
    seed = spec.get('seed', 1.0)
    sock = spec.get('socks', False)

    def fn(co, n):
        belly = clamp(-n.z * 0.9 + 0.15)
        c = mix(p, s, smoothstep(0.25, 0.75, belly))
        if sock and co.z < height_ref * 0.3:
            c = mix(c, s, 0.65)
        alpha = 0.0
        nz = noise.noise(co * 5.0 + Vector((seed, seed * 2, 0)))
        if pattern == 'spots' and noise.noise(co * 9.0 + Vector((seed, 0, seed))) > 0.38:
            c, alpha = a, glow
        elif pattern == 'stripes' and math.sin(co.y * 22.0 + nz * 3.0) > 0.72 and belly < 0.5:
            c, alpha = mix(c, a, 0.85), glow
        elif pattern == 'cracks' and abs(noise.noise(co * 4.0 + Vector((seed, 1, 2)))) < 0.05:
            c, alpha = a, glow
        v = 0.9 + 0.2 * (nz * 0.5 + 0.5)
        return (clamp(c[0] * v), clamp(c[1] * v), clamp(c[2] * v), alpha)
    return fn


def feature_part(parts, ob, color, alpha, bone):
    solid_paint(ob, hexcol(color) if isinstance(color, str) else color, alpha)
    set_group(ob, bone)
    parts.append(ob)


def eyes(parts, head, hs, fwd_off, color='#0b0b10', glow=0.0, side=0.42, up=0.2, size=0.2):
    for sx in (-1, 1):
        c = Vector(head) + Vector((sx * hs * side, -hs * fwd_off, hs * up))
        e = uv_sphere("eye", c, hs * size, seg=12, rings=8)
        feature_part(parts, e, color, glow, 'head')


def cone(name, base, tip, r0, r1=0.004, n=3, subdiv=2, bend=(0, 0, 0)):
    pts, rad = [], []
    for i in range(n + 1):
        t = i / n
        p = Vector(base).lerp(Vector(tip), t) + Vector(bend) * math.sin(math.pi * t)
        pts.append(p)
        rad.append(r0 * (1 - t) + r1 * t)
    return chain(pts, rad, name, subdiv=subdiv)


# ---------------------------------------------------------------------------
# ARCHETYPE : QUADRUPEDE
# ---------------------------------------------------------------------------

def build_quadruped(spec):
    L, H, G = spec['L'], spec['H'], spec['G']
    NL, NA, HS, SN = spec['NL'], math.radians(spec['NA']), spec['HS'], spec['SN']
    TL, TT, LR = spec['TL'], spec['TT'], spec['legR']
    gx = G * 0.55
    hips = Vector((0, L / 2, H))
    mid = Vector((0, 0, H + 0.02 * L))
    chest = Vector((0, -L / 2, H + 0.06 * L))
    neck_top = chest + Vector((0, -NL * math.cos(NA), NL * math.sin(NA)))
    head = neck_top + Vector((0, -HS * 0.55, HS * 0.15))
    snout = head + Vector((0, -SN - HS * 0.4, -HS * 0.25))

    nodes = [hips, mid, chest, neck_top, head, snout]
    radii = [G * 0.92, G * 0.95, G, G * spec.get('neckR', 0.55), HS, HS * 0.45]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
    legs = {}

    def add_leg(side, front):
        x = side * gx
        if front:
            top = Vector((x, -L / 2, H - 0.25 * G))
            knee = Vector((x, -L / 2 + 0.03 * H, 0.52 * H))
            foot = Vector((x, -L / 2 + 0.01 * H, 0.75 * LR))
            toe = Vector((x, -L / 2 - 0.14 * H - LR, 0.7 * LR))
            par = 2
        else:
            top = Vector((x, L / 2, H - 0.25 * G))
            knee = Vector((x, L / 2 - 0.06 * H, 0.55 * H))
            foot = Vector((x, L / 2 + 0.06 * H, 0.75 * LR))
            toe = Vector((x, L / 2 - 0.08 * H - LR, 0.7 * LR))
            par = 0
        base = len(nodes)
        nodes.extend([top, knee, foot, toe])
        radii.extend([LR * 1.7 if not front else LR * 1.5, LR * 1.05, LR * 0.8, LR * 0.85])
        edges.extend([(par, base), (base, base + 1), (base + 1, base + 2), (base + 2, base + 3)])
        legs[(side, front)] = (top, knee, foot, toe)

    for side in (1, -1):
        add_leg(side, True)
        add_leg(side, False)

    # queue
    tail_pts = []
    nseg = 5
    tu = math.radians(spec.get('tailUp', 20))
    t0 = hips + Vector((0, G * 0.75, 0.02))
    tail_pts.append(t0)
    b = len(nodes)
    nodes.append(t0)
    radii.append(TT)
    edges.append((0, b))
    for i in range(1, nseg + 1):
        t = i / nseg
        ang = tu + spec.get('tailCurl', 0.4) * t
        p = tail_pts[-1] + Vector((0, math.cos(ang), math.sin(ang))) * (TL / nseg)
        tail_pts.append(p)
        if spec.get('fluffyTail'):
            r = TT * (1.0 + 1.3 * math.sin(math.pi * min(1, t * 1.1)))
        else:
            r = TT * (1 - 0.75 * t)
        nodes.append(p)
        radii.append(max(r, 0.01))
        edges.append((len(nodes) - 2, len(nodes) - 1))

    body = skin_object("body", nodes, edges, radii, subdiv=2, branch=0.6)
    paint(body, body_painter(spec, H))

    # Os
    def tl(name, h, t, par):
        return (name, tuple(h), tuple(t), par)
    bones = [tl('root', (0, 0, 0), (0, 0, H * 0.3), None),
             tl('pelvis', hips, mid, 'root'),
             tl('spine', mid, chest, 'pelvis'),
             tl('neck', chest, neck_top, 'spine'),
             tl('head', neck_top, snout, 'neck')]
    tb = [(0, 2), (2, 4), (4, 5)]
    par = 'pelvis'
    for i, (a, c) in enumerate(tb):
        bones.append(tl('tail_%d' % (i + 1), tail_pts[a], tail_pts[c], par))
        par = 'tail_%d' % (i + 1)
    for (side, front), (top, knee, foot, toe) in legs.items():
        sfx = '_l' if side > 0 else '_r'
        if front:
            bones += [tl('upperarm' + sfx, top, knee, 'spine'), tl('forearm' + sfx, knee, foot, 'upperarm' + sfx),
                      tl('hand' + sfx, foot, toe, 'forearm' + sfx)]
        else:
            bones += [tl('thigh' + sfx, top, knee, 'pelvis'), tl('calf' + sfx, knee, foot, 'thigh' + sfx),
                      tl('foot' + sfx, foot, toe, 'calf' + sfx)]
    saddle = Vector((0, L * 0.05, H + G * 0.95))
    bones.append(tl('saddle', saddle, saddle + Vector((0, 0, 0.2)), 'spine'))
    auto_weights(body, bones)

    parts = [body]
    ctx = dict(spec=spec, head=head, snout=snout, neck_top=neck_top, chest=chest, mid=mid, hips=hips,
               tail=tail_pts, HS=HS, G=G, H=H, L=L)
    add_features(parts, ctx)
    mesh = join(parts, "SK_" + spec['name'])
    return mesh, bones, 'quadruped'


# ---------------------------------------------------------------------------
# ARCHETYPE : BIPEDE (golem, dresseur)
# ---------------------------------------------------------------------------

def build_biped(spec):
    S = spec['height']
    legH = S * spec.get('legRatio', 0.5)
    torso = S * spec.get('torsoRatio', 0.3)
    sx = S * spec.get('shoulderW', 0.12)
    armL = S * spec.get('armRatio', 0.36)
    hx = S * spec.get('hipW', 0.06)
    R = S * spec.get('girth', 0.09)
    LR = S * spec.get('limbR', 0.035)
    HR = S * spec.get('headR', 0.065)

    pelvis = Vector((0, 0, legH))
    waist = Vector((0, 0, legH + torso * 0.4))
    chest = Vector((0, 0, legH + torso))
    neck = Vector((0, 0, legH + torso + HR * 0.9))
    head = Vector((0, -HR * 0.08, legH + torso + HR * 1.9))
    headtop = head + Vector((0, 0.0, HR * 0.6))
    nodes = [pelvis, waist, chest, neck, head, headtop]
    radii = [R * 0.95, R * 0.85, R * 1.1, min(LR * 1.4, HR * 0.75), HR, HR * 0.8]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
    limbs = {}
    for side in (1, -1):
        x = side * hx
        top = Vector((x, 0, legH - LR * 0.5))
        knee = Vector((x, -0.02 * S, legH * 0.5))
        foot = Vector((x, 0.0, LR * 0.9))
        toe = Vector((x, -0.08 * S, LR * 0.7))
        b = len(nodes)
        nodes += [top, knee, foot, toe]
        radii += [LR * 1.5, LR * 1.05, LR * 0.9, LR * 0.8]
        edges += [(0, b), (b, b + 1), (b + 1, b + 2), (b + 2, b + 3)]
        sh = Vector((side * sx, 0, legH + torso * 0.92))
        elbow = sh + Vector((side * armL * 0.32, 0.01, -armL * 0.42))
        hand = sh + Vector((side * armL * 0.62, -0.02, -armL * 0.8))
        b2 = len(nodes)
        nodes += [sh, elbow, hand]
        radii += [LR * spec.get('armThick', 1.25), LR * spec.get('armThick', 1.25) * 0.85, LR * spec.get('handR', 1.1)]
        edges += [(2, b2), (b2, b2 + 1), (b2 + 1, b2 + 2)]
        limbs[side] = (top, knee, foot, toe, sh, elbow, hand)

    body = skin_object("body", nodes, edges, radii, subdiv=2, branch=0.7)
    if spec.get('human'):
        skin_c, jacket, pants, boots = (hexcol(c) for c in (spec['skin'], spec['primary'], spec['secondary'], '#2a2420'))
        acc = hexcol(spec['accent'])

        def fn(co, n):
            z = co.z
            if z > legH + torso + HR * 0.4:
                c = skin_c
            elif z > legH - 0.02 * S:
                c = jacket
                if abs(co.x) > sx + armL * 0.45:   # mains
                    c = skin_c
                elif abs(z - (legH + torso * 0.95)) < 0.025 * S:
                    c = acc   # echarpe
            elif z > S * 0.07:
                c = pants
            else:
                c = boots
            v = 0.94 + 0.08 * noise.noise(co * 30)
            return (c[0] * v, c[1] * v, c[2] * v, 0.0)
        paint(body, fn)
    else:
        paint(body, body_painter(spec, legH))

    def tl(name, h, t, par):
        return (name, tuple(h), tuple(t), par)
    bones = [tl('root', (0, 0, 0), (0, 0, legH * 0.3), None),
             tl('pelvis', pelvis, waist, 'root'),
             tl('spine', waist, chest, 'pelvis'),
             tl('neck', chest, neck, 'spine'),
             tl('head', neck, headtop, 'neck')]
    for side, (top, knee, foot, toe, sh, elbow, hand) in limbs.items():
        sfx = '_l' if side > 0 else '_r'
        bones += [tl('thigh' + sfx, top, knee, 'pelvis'), tl('calf' + sfx, knee, foot, 'thigh' + sfx),
                  tl('foot' + sfx, foot, toe, 'calf' + sfx),
                  tl('upperarm' + sfx, sh, elbow, 'spine'), tl('forearm' + sfx, elbow, hand, 'upperarm' + sfx)]
    bones.append(tl('saddle', chest + Vector((0, 0.1, 0.1)), chest + Vector((0, 0.1, 0.3)), 'spine'))
    bones.append(tl('hand_socket_r', limbs[-1][6], limbs[-1][6] + Vector((0, -0.05, -0.05)), 'forearm_r'))
    auto_weights(body, bones)
    parts = [body]
    ctx = dict(spec=spec, head=head, snout=head + Vector((0, -HR, 0)), neck_top=neck, chest=chest, mid=waist,
               hips=pelvis, tail=[pelvis, pelvis], HS=HR, G=R, H=legH, L=S * 0.3, limbs=limbs, S=S)
    add_features(parts, ctx)
    mesh = join(parts, "SK_" + spec['name'])
    return mesh, bones, 'biped'


# ---------------------------------------------------------------------------
# ARCHETYPE : AVIEN
# ---------------------------------------------------------------------------

def wing_mesh(side, shoulder, span, chord, color, accent, glow, name):
    """Aile plate (plumes) : bord d'attaque + bord de fuite festonne, epaissie."""
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    n = 8
    lead, trail = [], []
    for i in range(n + 1):
        t = i / n
        x = side * span * t
        y = -chord * 0.15 * math.sin(math.pi * t * 0.8)
        z = 0.15 * span * math.sin(math.pi * t * 0.5) * 0.3
        lead.append(bm.verts.new(Vector(shoulder) + Vector((x, y, z))))
        feather = chord * (1.0 - 0.55 * t) * (1.0 + 0.18 * (i % 2))
        trail.append(bm.verts.new(Vector(shoulder) + Vector((x + side * chord * 0.15 * t, y + feather, z - 0.02))))
    for i in range(n):
        if side > 0:
            bm.faces.new((lead[i], lead[i + 1], trail[i + 1], trail[i]))
        else:
            bm.faces.new((lead[i], trail[i], trail[i + 1], lead[i + 1]))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    so = ob.modifiers.new("solid", 'SOLIDIFY')
    so.thickness = chord * 0.06
    so.offset = 0
    sd = ob.modifiers.new("sub", 'SUBSURF')
    sd.levels = 2
    apply_mods(ob)
    c1, c2 = hexcol(color), hexcol(accent)

    def fn(co, nrm):
        t = abs(co.x - shoulder[0]) / span
        back = clamp((co.y - shoulder[1]) / chord)
        c = mix(c1, c2, smoothstep(0.45, 1.0, t * 0.6 + back * 0.6))
        a = glow * smoothstep(0.6, 1.0, t * 0.5 + back * 0.7)
        return (c[0], c[1], c[2], a)
    paint(ob, fn)
    return ob


def build_avian(spec):
    L, H, G = spec['L'], spec['H'], spec['G']
    HS, WS = spec['HS'], spec['wingspan']
    tail_end = Vector((0, L * 0.5, H + G * 0.1))
    belly = Vector((0, L * 0.05, H))
    chest = Vector((0, -L * 0.3, H + G * 0.3))
    neck_top = chest + Vector((0, -L * 0.12, spec.get('neckL', 0.3) * L))
    head = neck_top + Vector((0, -HS * 0.4, HS * 0.3))
    nodes = [tail_end, belly, chest, neck_top, head]
    radii = [G * 0.45, G, G * 0.95, G * 0.45, HS]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4)]
    LR = G * 0.12
    legs = {}
    for side in (1, -1):
        top = Vector((side * G * 0.4, L * 0.05, H - G * 0.6))
        knee = Vector((side * G * 0.45, L * 0.1, H * 0.45))
        foot = Vector((side * G * 0.45, L * 0.05, LR))
        toe = Vector((side * G * 0.45, -L * 0.08, LR * 0.8))
        b = len(nodes)
        nodes += [top, knee, foot, toe]
        radii += [LR * 2.2, LR, LR * 0.8, LR * 0.7]
        edges += [(1, b), (b, b + 1), (b + 1, b + 2), (b + 2, b + 3)]
        legs[side] = (top, knee, foot, toe)
    body = skin_object("body", nodes, edges, radii, subdiv=2, branch=0.6)
    paint(body, body_painter(spec, H))

    def tl(name, h, t, par):
        return (name, tuple(h), tuple(t), par)
    bones = [tl('root', (0, 0, 0), (0, 0, H * 0.3), None),
             tl('pelvis', tail_end, belly, 'root'),
             tl('spine', belly, chest, 'pelvis'),
             tl('neck', chest, neck_top, 'spine'),
             tl('head', neck_top, head + Vector((0, -HS, 0)), 'neck'),
             tl('tail_1', tail_end, tail_end + Vector((0, L * 0.4, -0.05)), 'pelvis')]
    for side, (top, knee, foot, toe) in legs.items():
        sfx = '_l' if side > 0 else '_r'
        bones += [tl('thigh' + sfx, top, knee, 'pelvis'), tl('calf' + sfx, knee, foot, 'thigh' + sfx),
                  tl('foot' + sfx, foot, toe, 'calf' + sfx)]
    parts = [body]
    auto_weights(body, bones)
    # ailes
    half = WS / 2
    for side in (1, -1):
        sfx = '_l' if side > 0 else '_r'
        sh = chest + Vector((side * G * 0.6, L * 0.05, G * 0.35))
        elbow = sh + Vector((side * half * 0.42, 0, half * 0.05))
        tip = sh + Vector((side * half, L * 0.1, half * 0.04))
        bones += [tl('wing_upper' + sfx, sh, elbow, 'spine'), tl('wing_lower' + sfx, elbow, tip, 'wing_upper' + sfx)]
        w = wing_mesh(side, sh, half, spec.get('chord', L * 0.55), spec['primary'], spec['wingTip'],
                      spec.get('wingGlow', 0.0), 'wing' + sfx)
        auto_weights(w, bones, allowed={'wing_upper' + sfx, 'wing_lower' + sfx, 'spine'}, falloff=3)
        parts.append(w)
    # plumes de queue
    for i in range(spec.get('tailFeathers', 3)):
        a = (i - (spec.get('tailFeathers', 3) - 1) / 2) * 0.35
        base = tail_end
        tip = base + Vector((math.sin(a) * L * 0.5, L * spec.get('tailLen', 0.6), -0.05 + abs(a) * 0.05))
        f = cone('tf', base, tip, G * 0.18, 0.01, n=3, bend=(0, 0, L * 0.05))
        feature_part(parts, f, spec['wingTip'], spec.get('tailGlow', 0.0), 'tail_1')
    saddle = Vector((0, L * 0.0, H + G * 0.9))
    bones.append(tl('saddle', saddle, saddle + Vector((0, 0, 0.2)), 'spine'))
    ctx = dict(spec=spec, head=head, snout=head + Vector((0, -HS, 0)), neck_top=neck_top, chest=chest, mid=belly,
               hips=tail_end, tail=[tail_end, tail_end], HS=HS, G=G, H=H, L=L)
    add_features(parts, ctx)
    mesh = join(parts, "SK_" + spec['name'])
    return mesh, bones, 'avian'


# ---------------------------------------------------------------------------
# ARCHETYPE : SERPENT
# ---------------------------------------------------------------------------

def build_serpent(spec):
    Ln, R, n = spec['length'], spec['radius'], 12
    pts, rad = [], []
    for i in range(n + 1):
        t = i / n
        y = -Ln * 0.5 + Ln * t
        x = math.sin(t * TAU * 0.9) * Ln * 0.06
        z = R * 1.05 + (0.6 * R * (1 - t) if t < 0.2 else 0)
        pts.append(Vector((x, y, z)))
        rad.append(R * (0.85 + 0.25 * math.sin(math.pi * min(1, t * 1.6))) * (1 - 0.85 * t ** 2))
    head = pts[0] + Vector((0, -R * 1.2, R * 0.2))
    nodes = [head] + pts
    radii = [R * 1.05] + rad
    body = chain(nodes, radii, "body")
    paint(body, body_painter(spec, R))

    def tl(name, h, t, par):
        return (name, tuple(h), tuple(t), par)
    bones = [tl('root', (0, 0, 0), (0, 0, R), None)]
    par = 'root'
    for k, i in enumerate(range(n, 2, -2)):
        nm = 'spine_%02d' % (k + 1)
        bones.append(tl(nm, pts[i], pts[i - 2], par))
        par = nm
    bones.append(tl('neck', pts[2], pts[0], par))
    bones.append(tl('head', pts[0], head + Vector((0, -R, 0)), 'neck'))
    auto_weights(body, bones)
    saddle = pts[3] + Vector((0, 0, R * 0.95))
    bones.append(tl('saddle', saddle, saddle + Vector((0, 0, 0.3)), 'spine_05'))
    parts = [body]
    ctx = dict(spec=spec, head=head, snout=head + Vector((0, -R, 0)), neck_top=pts[0], chest=pts[2], mid=pts[6],
               hips=pts[-1], tail=pts, HS=R * 1.05, G=R, H=R, L=Ln, spine=pts)
    add_features(parts, ctx)
    mesh = join(parts, "SK_" + spec['name'])
    return mesh, bones, 'serpent'


# ---------------------------------------------------------------------------
# ARCHETYPE : BLOB
# ---------------------------------------------------------------------------

def build_blob(spec):
    Rb = spec['R']
    ctr = Vector((0, 0, Rb * 0.95))
    body = uv_sphere("body", ctr, Rb, seg=40, rings=28)
    for v in body.data.vertices:
        lz = (v.co.z - ctr.z) / Rb
        k = 1.0 + 0.12 * (-lz)            # forme de goutte, plus large en bas
        v.co.x = ctr.x + (v.co.x - ctr.x) * k
        v.co.y = ctr.y + (v.co.y - ctr.y) * k
        if v.co.z < Rb * 0.18:              # base aplatie
            v.co.z = Rb * 0.18 - (Rb * 0.18 - v.co.z) * 0.25
    body.data.update()
    bottom = Vector((0, 0, Rb * 0.5))
    midp = ctr
    top = ctr + Vector((0, 0, Rb * 0.95))
    paint(body, body_painter(spec, Rb))
    def tl(name, h, t, par):
        return (name, tuple(h), tuple(t), par)
    bones = [tl('root', (0, 0, 0), (0, 0, Rb * 0.4), None),
             tl('pelvis', (0, 0, Rb * 0.3), bottom + Vector((0, 0, Rb * 0.3)), 'root'),
             tl('spine', bottom + Vector((0, 0, Rb * 0.3)), midp + Vector((0, 0, Rb * 0.2)), 'pelvis'),
             tl('head', midp + Vector((0, 0, Rb * 0.2)), top + Vector((0, 0, Rb * 0.5)), 'spine')]
    auto_weights(body, bones, falloff=2.5)
    parts = [body]
    head = ctr + Vector((0, 0, Rb * 0.1))
    ctx = dict(spec=spec, head=head, snout=head + Vector((0, -Rb, 0)), neck_top=top, chest=midp, mid=midp,
               hips=bottom, tail=[bottom, bottom], HS=Rb, G=Rb, H=Rb, L=Rb, blob=True)
    add_features(parts, ctx)
    saddle = top + Vector((0, 0, Rb * 0.5))
    bones.append(tl('saddle', saddle, saddle + Vector((0, 0, 0.1)), 'head'))
    mesh = join(parts, "SK_" + spec['name'])
    return mesh, bones, 'blob'


# ---------------------------------------------------------------------------
# Elements decoratifs (oreilles, cornes, bois, criniere, nageoires...)
# ---------------------------------------------------------------------------

def add_features(parts, c):
    spec = c['spec']
    HS, G = c['HS'], c['G']
    head, neck_top, chest, mid, hips = (Vector(c[k]) for k in ('head', 'neck_top', 'chest', 'mid', 'hips'))
    acc, prim, sec = spec['accent'], spec['primary'], spec['secondary']
    for feat in spec.get('features', []):
        kind = feat if isinstance(feat, str) else feat[0]
        opt = {} if isinstance(feat, str) else feat[1]
        if kind == 'eyes' and c.get('blob'):
            for sx in (-1, 1):
                dvec = Vector((sx * 0.38, -0.88, 0.28)).normalized()
                e = uv_sphere("eye", head + dvec * HS * 0.97, HS * opt.get('size', 0.13), seg=12, rings=8)
                feature_part(parts, e, opt.get('color', '#0b0b10'), opt.get('glow', 0.0), 'head')
        elif kind == 'eyes':
            eyes(parts, head, HS, opt.get('fwd', 0.75), opt.get('color', '#0b0b10'), opt.get('glow', 0.0),
                 side=opt.get('side', 0.42), up=opt.get('up', 0.22), size=opt.get('size', 0.2))
        elif kind == 'ears':
            size = opt.get('size', 1.0) * HS
            for sx in (-1, 1):
                base = head + Vector((sx * HS * 0.45, HS * 0.15, HS * 0.6))
                tip = base + Vector((sx * size * 0.35, size * 0.15, size * 1.1))
                e = cone('ear', base, tip, size * opt.get('width', 0.35), 0.005 if not opt.get('round') else size * 0.2)
                feature_part(parts, e, opt.get('color', prim), 0.0, 'head')
                if opt.get('tuft'):
                    t2 = cone('tuft', tip, tip + Vector((sx * 0.02, 0, size * 0.4)), size * 0.06, 0.002)
                    feature_part(parts, t2, '#111111', 0.0, 'head')
        elif kind == 'horns':
            size = opt.get('size', 1.0) * HS
            for sx in (-1, 1):
                base = head + Vector((sx * HS * 0.55, HS * 0.1, HS * 0.45))
                pts = [base, base + Vector((sx * size * 0.7, 0, size * 0.1)),
                       base + Vector((sx * size * 1.0, -size * 0.3, size * 0.5)),
                       base + Vector((sx * size * 0.9, -size * 0.55, size * 0.9))]
                h = chain(pts, [size * 0.22, size * 0.17, size * 0.1, 0.006], 'horn')
                feature_part(parts, h, opt.get('color', '#e8dcc0'), opt.get('glow', 0.0), 'head')
        elif kind == 'antlers':
            size = opt.get('size', 1.0) * HS
            col = opt.get('color', '#8a6d4e')
            for sx in (-1, 1):
                b0 = head + Vector((sx * HS * 0.35, HS * 0.2, HS * 0.6))
                b1 = b0 + Vector((sx * size * 0.6, size * 0.3, size * 0.9))
                b2 = b1 + Vector((sx * size * 0.5, size * 0.4, size * 0.9))
                b3 = b2 + Vector((sx * size * 0.2, size * 0.1, size * 0.8))
                pts = [b0, b1, b2, b3]
                tines = [(b1, Vector((sx * 0.1, -size * 0.5, size * 0.6))), (b2, Vector((sx * size * 0.1, -size * 0.6, size * 0.5))),
                         (b2, Vector((sx * size * 0.5, 0, size * 0.6)))]
                nodes, edges, radii = list(pts), [(0, 1), (1, 2), (2, 3)], [size * 0.12, size * 0.09, size * 0.07, 0.008]
                for (src, off) in tines:
                    si = pts.index(src)
                    nodes.append(src + off)
                    radii.append(0.006)
                    edges.append((si, len(nodes) - 1))
                a = skin_object('antler', nodes, edges, radii, subdiv=2)
                feature_part(parts, a, col, opt.get('glow', 0.0), 'head')
                if opt.get('crystals'):
                    for k in range(4):
                        p0 = nodes[random.randint(1, len(nodes) - 1)]
                        cr = cone('crystal', p0, p0 + Vector((random.uniform(-.2, .2), random.uniform(-.2, .2), 0.35)) * size,
                                  size * 0.07, 0.004, n=2, subdiv=1)
                        feature_part(parts, cr, acc, opt.get('crystalGlow', 1.0), 'head')
        elif kind == 'spikes':   # criniere / cristaux / flammes le long du dos
            count = opt.get('count', 6)
            size = opt.get('size', 0.5) * G
            for i in range(count):
                t = (i + 0.5) / count
                if opt.get('along') == 'neck':
                    base = chest.lerp(head, t * 0.9)
                    up = Vector((0, 0.35, 1)).normalized()
                elif opt.get('along') == 'spine' and 'spine' in c:
                    sp = c['spine']
                    base = sp[min(len(sp) - 1, int(t * (len(sp) - 1)))]
                    up = Vector((0, 0.2, 1)).normalized()
                elif opt.get('along') == 'shoulders':
                    sd = 1 if i % 2 == 0 else -1
                    base = chest + Vector((sd * G * 1.15, 0.05 * G, G * 0.05))
                    up = Vector((sd * 0.5, 0.2, 1)).normalized()
                elif opt.get('along') == 'top':
                    ang = TAU * i / count
                    base = neck_top + Vector((math.cos(ang) * G * 0.35, math.sin(ang) * G * 0.35, -G * 0.2))
                    up = Vector((math.cos(ang) * 0.5, math.sin(ang) * 0.5, 1)).normalized()
                else:
                    base = hips.lerp(chest, 1 - t)
                    up = Vector((0, 0.45, 1)).normalized()
                base = base + Vector((0, 0, opt.get('lift', 0.85) * (G if opt.get('along') not in ('top', 'shoulders') else 0)))
                h = size * (0.6 + 0.6 * math.sin(math.pi * t)) * random.uniform(0.85, 1.15)
                s = cone('spike', base, base + up * h, h * opt.get('width', 0.28), 0.004, n=2, subdiv=1,
                         bend=(0, h * opt.get('curl', 0.15), 0))
                bone = opt.get('bone') or ('neck' if opt.get('along') == 'neck' else 'spine')
                if opt.get('along') == 'spine' and 'spine' in c:
                    bone = 'spine_%02d' % max(1, min(5, 5 - int(t * 5)))
                if opt.get('along') == 'top':
                    bone = 'head'
                feature_part(parts, s, opt.get('color', acc), opt.get('glow', 0.0), bone)
        elif kind == 'tailtip':     # flamme / touffe au bout de la queue
            tail = c['tail']
            base = Vector(tail[-1])
            d = (Vector(tail[-1]) - Vector(tail[-2])).normalized() if len(tail) > 1 else Vector((0, 1, 0))
            size = opt.get('size', 1.0) * G
            f = cone('tailtip', base - d * size * 0.2, base + d * size * 0.9 + Vector((0, 0, size * 0.5)), size * 0.35, 0.004,
                     n=3, bend=(0, 0, size * 0.2))
            bones = 'tail_3' if spec['archetype'] == 'quadruped' else ('spine_01' if spec['archetype'] == 'serpent' else 'tail_1')
            feature_part(parts, f, opt.get('color', acc), opt.get('glow', 1.0), bones)
        elif kind == 'fins':
            count = opt.get('count', 4)
            size = opt.get('size', 0.6) * G
            sp = c.get('spine') or [hips.lerp(chest, k / 6) for k in range(7)]
            for i in range(count):
                t = (i + 0.5) / count
                idx = int(t * (len(sp) - 1))
                base = Vector(sp[idx]) + Vector((0, 0, G * 0.85))
                f = cone('fin', base, base + Vector((0, size * 0.8, size)), size * 0.45, 0.004, n=2)
                f.data.transform(Matrix.Translation(base) @ Matrix.Diagonal((0.2, 1, 1, 1)) @ Matrix.Translation(-base))
                bone = ('spine_%02d' % max(1, min(5, 5 - int(t * 5)))) if 'spine' in c else 'spine'
                feature_part(parts, f, opt.get('color', acc), opt.get('glow', 0.0), bone)
        elif kind == 'beak':
            size = opt.get('size', 1.0) * HS
            base = head + Vector((0, -HS * 0.7, -HS * 0.05))
            b = cone('beak', base, base + Vector((0, -size, -size * 0.25)), HS * 0.38, 0.004, n=2, bend=(0, 0, -size * 0.1))
            feature_part(parts, b, opt.get('color', '#f0b030'), 0.0, 'head')
        elif kind == 'crest':
            n = opt.get('count', 3)
            size = opt.get('size', 1.0) * HS
            for i in range(n):
                a = (i - (n - 1) / 2) * 0.35
                base = head + Vector((math.sin(a) * HS * 0.3, HS * 0.2, HS * 0.7))
                tip = base + Vector((math.sin(a) * size * 0.4, size * 0.9, size * 0.7))
                cr = cone('crest', base, tip, HS * 0.12, 0.004, n=3, bend=(0, 0, size * 0.2))
                feature_part(parts, cr, opt.get('color', acc), opt.get('glow', 0.0), 'head')
        elif kind == 'leaves':
            n = opt.get('count', 5)
            size = opt.get('size', 0.6) * G
            for i in range(n):
                ang = TAU * i / n + 0.3
                if opt.get('on') == 'head' and c.get('blob'):
                    base = Vector(c['neck_top']) - Vector((0, 0, HS * 0.12))
                    bone = 'head'
                elif opt.get('on') == 'head':
                    base = head + Vector((0, HS * 0.2, HS * 0.8))
                    bone = 'head'
                else:
                    base = mid + Vector((0, 0, G * 0.9))
                    bone = 'spine'
                d = Vector((math.cos(ang) * 0.7, math.sin(ang) * 0.7, 0.8)).normalized()
                lf = cone('leaf', base, base + d * size, size * 0.35, 0.004, n=3, bend=(0, 0, size * 0.15))
                lf.data.transform(Matrix.Translation(base) @ Matrix.Diagonal((1, 1, 0.35, 1)) @ Matrix.Translation(-base))
                feature_part(parts, lf, opt.get('color', acc), opt.get('glow', 0.0), bone)
            if opt.get('flower'):
                fl = uv_sphere('flower', base + Vector((0, 0, size * 0.25)), size * 0.25)
                feature_part(parts, fl, opt['flower'], 0.2, bone)
        elif kind == 'antenna':
            for sx in (-1, 1):
                base = Vector(c['neck_top']) + Vector((sx * HS * 0.25, 0, -HS * 0.1))
                tip = base + Vector((sx * HS * 0.35, -HS * 0.1, HS * 0.9))
                a = cone('ant', base, tip, HS * 0.05, HS * 0.03, n=3, bend=(0, -HS * 0.15, 0))
                feature_part(parts, a, prim, 0.0, 'head')
                ball = uv_sphere('antball', tip, HS * 0.16)
                feature_part(parts, ball, acc, opt.get('glow', 3.0), 'head')
        elif kind == 'backpack':
            S = c['S']
            chestv = Vector(c['chest'])
            bp = chain([chestv + Vector((0, S * 0.1, -S * 0.04)), chestv + Vector((0, S * 0.11, -S * 0.16))],
                       [S * 0.065, S * 0.06], 'pack', subdiv=1, scale=(1.3, 0.8, 1.0))
            feature_part(parts, bp, '#5b4632', 0.0, 'spine')
            # petites capsules a la ceinture
            for k in range(4):
                cp = uv_sphere('caps', Vector(c['hips']) + Vector((-S * 0.05 + k * S * 0.033, -S * 0.065, S * 0.01)), S * 0.012)
                feature_part(parts, cp, '#7fe8ff', 2.0, 'pelvis')
        elif kind == 'hair':
            S = c['S']
            h = uv_sphere('hair', head + Vector((0, HS * 0.15, HS * 0.25)), HS * 1.05, scale=(1.0, 1.05, 0.85))
            feature_part(parts, h, opt.get('color', '#3a2a1e'), 0.0, 'head')
        elif kind == 'snout_glow':
            g = uv_sphere('glow', Vector(c['snout']), HS * 0.2)
            feature_part(parts, g, acc, opt.get('glow', 2.0), 'head')


# ---------------------------------------------------------------------------
# Animations par archetype
# ---------------------------------------------------------------------------

def anims_quadruped(arm, spec):
    H = spec['H']
    s = spec.get('animScale', 1.0)

    def legs(d, ph, amp, bound=False):
        for side, off in (('_l', 0.0), ('_r', math.pi)):
            pb = ph + (0 if bound else off)
            pf = ph + (math.pi if not bound else math.pi * 0.6) + (0 if bound else off)
            for limb, low, p in (('thigh', 'calf', pb), ('upperarm', 'forearm', pf)):
                P(d, limb + side, r=[(X, -amp * math.sin(p))])
                lift = max(0.0, -math.cos(p))
                P(d, low + side, r=[(X, (amp * 1.3 if limb == 'thigh' else -amp * 1.3) * lift)])

    def idle(t):
        d = {}
        p = TAU * t
        P(d, 'spine', r=[(X, 0.03 * math.sin(p))])
        P(d, 'neck', r=[(Z, 0.18 * math.sin(p)), (X, 0.05 * math.sin(2 * p))])
        P(d, 'head', r=[(X, -0.06 * math.sin(p + 1))])
        for i in range(1, 4):
            P(d, 'tail_%d' % i, r=[(Z, 0.22 * math.sin(p * 2 - i * 0.6))])
        P(d, 'root', l=(0, 0, 0.012 * H * math.sin(2 * p)))
        return d

    def walk(t):
        d = {}
        p = TAU * t
        legs(d, p, 0.42 * s)
        P(d, 'root', l=(0, 0, 0.025 * H * abs(math.sin(p))))
        P(d, 'spine', r=[(Z, 0.05 * math.sin(p))])
        P(d, 'neck', r=[(X, 0.05 * math.sin(2 * p))])
        for i in range(1, 4):
            P(d, 'tail_%d' % i, r=[(Z, 0.18 * math.sin(p - i * 0.7))])
        return d

    def run(t):
        d = {}
        p = TAU * t
        legs(d, p, 0.75 * s, bound=True)
        P(d, 'root', l=(0, 0, 0.08 * H * max(0, math.sin(p))))
        P(d, 'pelvis', r=[(X, 0.12 * math.sin(p))])
        P(d, 'spine', r=[(X, -0.15 * math.sin(p))])
        P(d, 'neck', r=[(X, 0.12 * math.sin(p + 1))])
        for i in range(1, 4):
            P(d, 'tail_%d' % i, r=[(X, 0.15 * math.sin(p - i * 0.7))])
        return d

    def attack(t):
        d = {}
        e = math.sin(math.pi * clamp(t / 0.55)) if t < 0.55 else 0.0
        back = math.sin(math.pi * clamp(t / 0.25)) * (1 if t < 0.25 else 0)
        P(d, 'root', l=(0, -0.35 * spec['L'] * e + 0.1 * spec['L'] * back, 0.1 * H * e))
        P(d, 'spine', r=[(X, -0.25 * e + 0.15 * back)])
        P(d, 'neck', r=[(X, 0.45 * e - 0.3 * back)])
        P(d, 'head', r=[(X, -0.35 * e)])
        for sfx in ('_l', '_r'):
            P(d, 'upperarm' + sfx, r=[(X, 0.7 * e)])
            P(d, 'forearm' + sfx, r=[(X, -0.6 * e)])
            P(d, 'thigh' + sfx, r=[(X, -0.3 * e)])
        return d

    def swim(t):
        d = {}
        p = TAU * t
        legs(d, p, 0.6 * s)
        P(d, 'spine', r=[(Z, 0.12 * math.sin(p))])
        P(d, 'pelvis', r=[(Z, -0.12 * math.sin(p))])
        for i in range(1, 4):
            P(d, 'tail_%d' % i, r=[(Z, 0.35 * math.sin(p - i * 0.8))])
        return d

    make_action(arm, 'Idle', 60, idle)
    make_action(arm, 'Walk', 30, walk)
    make_action(arm, 'Run', 18, run)
    make_action(arm, 'Attack', 24, attack)
    make_action(arm, 'Swim', 36, swim)


def anims_biped(arm, spec):
    human = spec.get('human', False)

    def limbs(d, p, amp, arm_amp):
        for sfx, off in (('_l', 0), ('_r', math.pi)):
            q = p + off
            P(d, 'thigh' + sfx, r=[(X, -amp * math.sin(q))])
            P(d, 'calf' + sfx, r=[(X, amp * 1.4 * max(0, -math.cos(q)))])
            P(d, 'upperarm' + sfx, r=[(X, arm_amp * math.sin(q))])
            P(d, 'forearm' + sfx, r=[(X, -0.3 * arm_amp - 0.2)])

    def idle(t):
        d = {}
        p = TAU * t
        P(d, 'spine', r=[(X, 0.02 * math.sin(p))])
        P(d, 'neck', r=[(Z, 0.12 * math.sin(p))])
        for sfx, sg in (('_l', 1), ('_r', -1)):
            P(d, 'upperarm' + sfx, r=[(Y, sg * 0.05 * math.sin(p))])
        P(d, 'root', l=(0, 0, -0.006 * spec['height'] * (1 + math.sin(2 * p))))
        return d

    def walk(t):
        d = {}
        p = TAU * t
        limbs(d, p, 0.45, 0.4)
        P(d, 'root', l=(0, 0, 0.015 * spec['height'] * abs(math.sin(p))))
        P(d, 'spine', r=[(Z, 0.06 * math.sin(p))])
        return d

    def run(t):
        d = {}
        p = TAU * t
        limbs(d, p, 0.8, 0.8)
        P(d, 'root', l=(0, 0, 0.04 * spec['height'] * abs(math.sin(p))))
        P(d, 'spine', r=[(X, -0.15), (Z, 0.1 * math.sin(p))])
        return d

    def attack(t):   # coup de poing / lancer
        d = {}
        wind = math.sin(math.pi * clamp(t / 0.35)) if t < 0.35 else 0
        hit = math.sin(math.pi * clamp((t - 0.3) / 0.45)) if 0.3 < t < 0.75 else 0
        P(d, 'spine', r=[(Z, 0.4 * wind - 0.5 * hit)])
        P(d, 'upperarm_r', r=[(X, 1.6 * wind - 1.9 * hit)])
        P(d, 'forearm_r', r=[(X, -0.9 * wind)])
        P(d, 'thigh_l', r=[(X, -0.3 * hit)])
        return d

    def ride(t):
        d = {}
        p = TAU * t
        for sfx, sg in (('_l', 1), ('_r', -1)):
            P(d, 'thigh' + sfx, r=[(X, -1.35), (Y, sg * 0.35)])
            P(d, 'calf' + sfx, r=[(X, 1.4)])
            P(d, 'upperarm' + sfx, r=[(X, -0.7), (Y, sg * 0.4)])
            P(d, 'forearm' + sfx, r=[(X, -0.5)])
        P(d, 'spine', r=[(X, -0.15 + 0.03 * math.sin(p))])
        return d

    def swim(t):
        d = {}
        p = TAU * t
        P(d, 'pelvis', r=[(X, -1.2)])
        for sfx, off in (('_l', 0), ('_r', math.pi)):
            P(d, 'upperarm' + sfx, r=[(X, -1.5 + 1.2 * math.sin(p + off))])
            P(d, 'thigh' + sfx, r=[(X, 0.3 * math.sin(2 * p + off))])
        return d

    make_action(arm, 'Idle', 60, idle)
    make_action(arm, 'Walk', 32, walk)
    make_action(arm, 'Run', 20, run)
    make_action(arm, 'Attack' if not human else 'Throw', 24, attack)
    if human:
        make_action(arm, 'Ride', 40, ride)
        make_action(arm, 'Swim', 40, swim)


def anims_avian(arm, spec):
    def fold(d, amt):
        for sfx, sg in (('_l', 1), ('_r', -1)):
            P(d, 'wing_upper' + sfx, r=[(Z, sg * 1.3 * amt), (Y, sg * 0.35 * amt)])
            P(d, 'wing_lower' + sfx, r=[(Z, sg * 0.25 * amt)])

    def idle(t):
        d = {}
        p = TAU * t
        fold(d, 1.0)
        P(d, 'neck', r=[(Z, 0.25 * math.sin(p)), (X, 0.08 * math.sin(2 * p))])
        P(d, 'tail_1', r=[(X, 0.08 * math.sin(p))])
        return d

    def walk(t):
        d = {}
        p = TAU * t
        fold(d, 1.0)
        for sfx, off in (('_l', 0), ('_r', math.pi)):
            P(d, 'thigh' + sfx, r=[(X, -0.5 * math.sin(p + off))])
            P(d, 'calf' + sfx, r=[(X, 0.6 * max(0, -math.cos(p + off)))])
        P(d, 'neck', r=[(X, 0.15 * math.sin(2 * p))])
        P(d, 'root', l=(0, 0, 0.03 * spec['H'] * abs(math.sin(p))))
        return d

    def fly(t):
        d = {}
        p = TAU * t
        for sfx, sg in (('_l', 1), ('_r', -1)):
            P(d, 'wing_upper' + sfx, r=[(Y, sg * 0.75 * math.sin(p))])
            P(d, 'wing_lower' + sfx, r=[(Y, sg * 0.45 * math.sin(p - 0.7))])
            P(d, 'thigh' + sfx, r=[(X, 1.0)])
            P(d, 'calf' + sfx, r=[(X, -0.6)])
        P(d, 'root', l=(0, 0, -0.06 * spec['H'] * math.sin(p)))
        P(d, 'tail_1', r=[(X, 0.1 * math.sin(p + 1))])
        return d

    def attack(t):
        d = {}
        e = math.sin(math.pi * clamp(t / 0.6)) if t < 0.6 else 0
        for sfx, sg in (('_l', 1), ('_r', -1)):
            P(d, 'wing_upper' + sfx, r=[(Y, -sg * 0.9 * e)])
        P(d, 'neck', r=[(X, 0.5 * e)])
        P(d, 'root', l=(0, -0.4 * spec['L'] * e, 0.1 * spec['H'] * e))
        return d

    make_action(arm, 'Idle', 60, idle)
    make_action(arm, 'Walk', 24, walk)
    make_action(arm, 'Fly', 24, fly)
    make_action(arm, 'Attack', 24, attack)


def anims_serpent(arm, spec):
    spines = sorted([b.name for b in arm.data.bones if b.name.startswith('spine_')])

    def wave(d, p, amp, k):
        for i, nm in enumerate(spines):
            P(d, nm, r=[(Z, amp * math.sin(p - i * k))])

    def idle(t):
        d = {}
        p = TAU * t
        wave(d, p, 0.08, 0.9)
        P(d, 'neck', r=[(X, -0.35 + 0.05 * math.sin(p))])
        P(d, 'head', r=[(X, 0.3)])
        return d

    def swim(t):
        d = {}
        wave(d, TAU * t, 0.28, 1.1)
        P(d, 'head', r=[(Z, -0.15 * math.sin(TAU * t))])
        return d

    def attack(t):
        d = {}
        e = math.sin(math.pi * clamp(t / 0.6)) if t < 0.6 else 0
        rear = math.sin(math.pi * clamp(t / 0.3)) if t < 0.3 else 0
        P(d, 'neck', r=[(X, -0.6 * rear + 0.4 * e)])
        P(d, 'head', r=[(X, -0.3 * e)])
        P(d, 'root', l=(0, -0.08 * spec['length'] * e, 0))
        return d

    make_action(arm, 'Idle', 60, idle)
    make_action(arm, 'Swim', 40, swim)
    make_action(arm, 'Walk', 40, swim)
    make_action(arm, 'Attack', 30, attack)


def anims_blob(arm, spec):
    R = spec['R']

    def idle(t):
        d = {}
        p = TAU * t
        P(d, 'spine', s=(1 + 0.04 * math.sin(p), 1 + 0.04 * math.sin(p), 1 - 0.04 * math.sin(p)))
        P(d, 'head', r=[(Z, 0.15 * math.sin(p))])
        return d

    def walk(t):
        d = {}
        p = TAU * t
        h = abs(math.sin(p))
        P(d, 'root', l=(0, 0, 0.5 * R * h))
        sq = 1 - 0.18 * (1 - h) ** 4
        P(d, 'pelvis', s=(2 - sq, 2 - sq, sq))
        P(d, 'head', r=[(X, 0.1 * math.sin(p))])
        return d

    def attack(t):
        d = {}
        e = math.sin(math.pi * clamp(t / 0.6)) if t < 0.6 else 0
        P(d, 'root', l=(0, -1.2 * R * e, 0.4 * R * e))
        P(d, 'spine', s=(1 - 0.15 * e, 1 + 0.3 * e, 1 - 0.1 * e))
        return d

    make_action(arm, 'Idle', 60, idle)
    make_action(arm, 'Walk', 20, walk)
    make_action(arm, 'Attack', 24, attack)


# ---------------------------------------------------------------------------
# Catalogue des creatures (memes identifiants que Content/Data/species.json)
# ---------------------------------------------------------------------------

CREATURES = [
    dict(name='Braisillon', archetype='quadruped', L=0.42, H=0.26, G=0.13, NL=0.13, NA=45, HS=0.11, SN=0.08, TL=0.38, TT=0.06,
         legR=0.032, fluffyTail=True, tailUp=35, primary='#e0612a', secondary='#f7e3c8', accent='#ffb000', socks=True,
         features=[('ears', dict(size=1.3, width=0.4)), ('tailtip', dict(size=1.2, glow=4.0)), ('eyes', {})]),
    dict(name='Pyrolynx', archetype='quadruped', L=1.15, H=0.85, G=0.34, NL=0.34, NA=40, HS=0.24, SN=0.15, TL=0.85, TT=0.11,
         legR=0.085, tailUp=15, primary='#b8321a', secondary='#2b1a14', accent='#ff7a1a', pattern='stripes', pattern_glow=0.6,
         features=[('ears', dict(size=1.0, tuft=True)), ('spikes', dict(along='neck', count=7, size=0.9, glow=5.0, curl=0.4)),
                   ('spikes', dict(count=6, size=0.6, glow=4.0, curl=0.3)), ('tailtip', dict(size=1.0, glow=6.0)), ('eyes', {})]),
    dict(name='Ondrelle', archetype='quadruped', L=0.55, H=0.15, G=0.11, NL=0.09, NA=25, HS=0.095, SN=0.06, TL=0.45, TT=0.07,
         legR=0.028, tailUp=-5, tailCurl=0.0, primary='#3b7fb8', secondary='#cfe8f2', accent='#6fe0ff',
         features=[('ears', dict(size=0.45, round=True, width=0.6)), ('fins', dict(count=3, size=0.9, glow=1.0)), ('eyes', {})]),
    dict(name='Nereon', archetype='quadruped', L=1.6, H=0.62, G=0.38, NL=0.42, NA=35, HS=0.25, SN=0.2, TL=1.3, TT=0.2,
         legR=0.1, tailUp=0, tailCurl=0.1, primary='#1f5f8b', secondary='#a8e0ec', accent='#5ff0ff', pattern='spots', pattern_glow=1.5,
         features=[('fins', dict(count=5, size=0.9, glow=2.5)), ('crest', dict(count=3, size=1.4, glow=1.5)), ('eyes', {})]),
    dict(name='Feuillouve', archetype='quadruped', L=0.5, H=0.3, G=0.12, NL=0.15, NA=40, HS=0.105, SN=0.1, TL=0.34, TT=0.055,
         legR=0.032, fluffyTail=True, primary='#5e8c3a', secondary='#e8e2c0', accent='#9be05a', socks=True,
         features=[('ears', dict(size=1.2, color='#7bb04a')), ('leaves', dict(count=5, size=1.4)), ('eyes', {})]),
    dict(name='Sylvecerf', archetype='quadruped', L=1.3, H=1.05, G=0.32, NL=0.55, NA=58, HS=0.2, SN=0.22, TL=0.2, TT=0.07,
         legR=0.065, primary='#6b4a2e', secondary='#d9c9a3', accent='#7fd65a', pattern='spots', pattern_glow=0.0, neckR=0.5,
         features=[('ears', dict(size=0.9, width=0.45)), ('antlers', dict(size=2.2, color='#5d4630')),
                   ('leaves', dict(count=4, size=0.8, on='head', glow=0.8)), ('eyes', {})]),
    dict(name='Moussibul', archetype='blob', R=0.3, primary='#6fa04a', secondary='#c9d98a', accent='#3f7a2a',
         features=[('leaves', dict(count=6, size=1.0, on='head', flower='#e85da0')), ('eyes', dict(fwd=0.95, size=0.12, up=0.1))]),
    dict(name='Galetor', archetype='biped', height=2.2, legRatio=0.38, torsoRatio=0.33, shoulderW=0.2, armRatio=0.45,
         hipW=0.09, girth=0.16, limbR=0.06, headR=0.1, armThick=1.6, handR=1.7,
         primary='#7a7468', secondary='#4c4842', accent='#ffb347', pattern='cracks', pattern_glow=4.0,
         features=[('spikes', dict(along='shoulders', count=6, size=0.9, color='#5a554c', bone='spine')),
                   ('eyes', dict(color='#ffcf6a', glow=6.0, fwd=0.8, size=0.18))]),
    dict(name='Volterelle', archetype='avian', L=0.32, H=0.16, G=0.09, HS=0.07, wingspan=0.9, neckL=0.35, chord=0.16,
         primary='#f2d43a', secondary='#2e3a59', accent='#9be7ff', wingTip='#2e3a59', tailFeathers=3, tailLen=0.6,
         features=[('beak', dict(size=1.0, color='#2e3a59')), ('crest', dict(count=3, size=1.2, glow=4.0)), ('eyes', {})]),
    dict(name='Orajaile', archetype='avian', L=1.7, H=0.9, G=0.42, HS=0.3, wingspan=5.2, neckL=0.4, chord=0.95,
         primary='#2f3e6b', secondary='#c7d3f0', accent='#8fe3ff', wingTip='#8fe3ff', wingGlow=2.5, tailFeathers=5, tailLen=0.9,
         tailGlow=1.5, pattern='stripes', pattern_glow=1.2,
         features=[('beak', dict(size=1.2, color='#d9e2f5')), ('crest', dict(count=5, size=1.6, glow=3.0)),
                   ('horns', dict(size=0.9, color='#c7d3f0')), ('eyes', dict(color='#8fe3ff', glow=3.0))]),
    dict(name='Givrelan', archetype='quadruped', L=1.4, H=1.1, G=0.37, NL=0.5, NA=50, HS=0.22, SN=0.22, TL=0.15, TT=0.06,
         legR=0.075, primary='#dde8f2', secondary='#8aa6bd', accent='#7fdbff', neckR=0.6, socks=True,
         features=[('ears', dict(size=0.8)), ('antlers', dict(size=2.0, color='#bfe9ff', glow=0.5, crystals=True, crystalGlow=2.5)),
                   ('spikes', dict(along='neck', count=5, size=0.5, color='#ffffff', glow=0.3)), ('eyes', {})]),
    dict(name='Nocthys', archetype='quadruped', L=0.7, H=0.45, G=0.16, NL=0.18, NA=35, HS=0.14, SN=0.08, TL=0.55, TT=0.05,
         legR=0.045, tailUp=10, primary='#1e1b2e', secondary='#3e3760', accent='#b47cff', pattern='spots', pattern_glow=3.0,
         features=[('ears', dict(size=1.1, tuft=True)), ('eyes', dict(color='#c9a0ff', glow=8.0, size=0.24)),
                   ('tailtip', dict(size=0.7, glow=3.0))]),
    dict(name='Marevore', archetype='serpent', length=12.0, radius=0.55, primary='#123e5c', secondary='#5fb3c9', accent='#3fffe0',
         pattern='spots', pattern_glow=2.0,
         features=[('fins', dict(count=7, size=1.6, glow=2.0)), ('horns', dict(size=0.9, color='#a8f0e8')),
                   ('crest', dict(count=3, size=1.2, glow=2.0)), ('eyes', dict(color='#3fffe0', glow=5.0, size=0.18)),
                   ('tailtip', dict(size=2.5, glow=2.0))]),
    dict(name='Solarion', archetype='avian', L=1.9, H=1.0, G=0.45, HS=0.3, wingspan=6.0, neckL=0.5, chord=1.1,
         primary='#ffe7a3', secondary='#ff8a2a', accent='#fff3c4', wingTip='#ff8a2a', wingGlow=4.0, tailFeathers=7,
         tailLen=1.4, tailGlow=6.0,
         features=[('beak', dict(size=1.1, color='#ffcf5a')), ('crest', dict(count=5, size=2.2, glow=6.0)),
                   ('eyes', dict(color='#ffffff', glow=6.0))]),
    dict(name='Cendrebuffle', archetype='quadruped', L=1.35, H=0.78, G=0.5, NL=0.22, NA=12, HS=0.3, SN=0.2, TL=0.5, TT=0.05,
         legR=0.12, tailUp=-30, primary='#3a2f2a', secondary='#6e5c50', accent='#ff5a1f', pattern='cracks', pattern_glow=5.0,
         features=[('horns', dict(size=1.3, color='#e8dcc0')), ('ears', dict(size=0.5, width=0.5)),
                   ('spikes', dict(count=5, size=0.45, color='#2a221e', glow=0.0)), ('eyes', dict(color='#ff8a3a', glow=4.0))]),
    dict(name='Lumiole', archetype='blob', R=0.17, primary='#f5f0d0', secondary='#9ad0ff', accent='#fff27a', pattern='spots',
         pattern_glow=2.0, features=[('antenna', dict(glow=6.0)), ('eyes', dict(fwd=0.95, size=0.14, up=0.15))]),
    dict(name='Grelichon', archetype='blob', R=0.22, primary='#e8f6ff', secondary='#b4d8f0', accent='#8fe8ff',
         features=[('spikes', dict(along='top', count=7, size=0.9, glow=1.5, width=0.3)), ('eyes', dict(fwd=0.95, size=0.13))]),
]

TAMER = dict(name='Tamer', archetype='biped', human=True, height=1.76, legRatio=0.5, torsoRatio=0.27, shoulderW=0.115,
             armRatio=0.36, hipW=0.055, girth=0.085, limbR=0.032, headR=0.066, armThick=1.15, handR=1.0,
             skin='#e0b89a', primary='#2f5d50', secondary='#3b3f4a', accent='#d94f30',
             features=[('backpack', {}), ('hair', {}), ('eyes', dict(fwd=0.85, size=0.13, up=0.15, side=0.38))])

ANIMS = dict(quadruped=anims_quadruped, biped=anims_biped, avian=anims_avian, serpent=anims_serpent, blob=anims_blob)
BUILD = dict(quadruped=build_quadruped, biped=build_biped, avian=build_avian, serpent=build_serpent, blob=build_blob)


def build_character(spec, out_dir, preview_dir):
    reset_scene()
    random.seed(zlib.crc32(spec['name'].encode()))
    mesh, bones, arch = BUILD[spec['archetype']](spec)
    arm = build_armature(bones)
    mesh.parent = arm
    md = mesh.modifiers.new("Armature", 'ARMATURE')
    md.object = arm
    ANIMS[arch](arm, spec)
    arm.animation_data.action = bpy.data.actions.get('Idle')
    folder = os.path.join(out_dir, 'Creatures' if spec is not TAMER else 'Characters', spec['name'])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, 'SK_%s.fbx' % spec['name'])
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'ARMATURE', 'MESH'},
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', add_leaf_bones=False,
                             bake_anim=True, bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False,
                             bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0,
                             mesh_smooth_type='FACE', colors_type='SRGB', primary_bone_axis='Y',
                             secondary_bone_axis='X', armature_nodetype='NULL', use_armature_deform_only=False)
    tris = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    print("[OK] %-13s %-10s %6d tris  %2d os  %d anims -> %s" % (spec['name'], arch, tris, len(bones),
                                                                  len(bpy.data.actions), path))
    if preview_dir:
        # pose de presentation : frame 10 de l'idle
        bpy.context.scene.frame_set(10)
        render_preview(mesh, os.path.join(preview_dir, spec['name'] + '.png'))
    return path


# ---------------------------------------------------------------------------
# Environnement (maillages statiques)
# ---------------------------------------------------------------------------

def displace(ob, strength, size, kind='CLOUDS', levels=3):
    sd = ob.modifiers.new('sd', 'SUBSURF')
    sd.levels = levels
    sd.render_levels = levels
    tex = bpy.data.textures.new('t', kind)
    tex.noise_scale = size
    if kind == 'VORONOI':
        tex.distance_metric = 'DISTANCE'
    d = ob.modifiers.new('disp', 'DISPLACE')
    d.texture = tex
    d.strength = strength
    d.texture_coords = 'LOCAL'
    apply_mods(ob)


def rock(name, size, seed, flat=1.0, base='#8d8a82', moss=True):
    random.seed(seed)
    ob = uv_sphere(name, (0, 0, 0), size, seg=14, rings=9, scale=(random.uniform(0.8, 1.3), random.uniform(0.8, 1.2), 0.75 * flat))
    displace(ob, size * 0.35, size * 0.8, 'VORONOI', levels=3)
    displace(ob, size * 0.08, size * 0.15, 'CLOUDS', levels=0)
    me = ob.data
    zmin = min(v.co.z for v in me.vertices)
    me.transform(Matrix.Translation((0, 0, -zmin - size * 0.25)))
    c0, mossc = hexcol(base), hexcol('#4d6b2f')

    def fn(co, n):
        v = 0.75 + 0.35 * (noise.noise(co * 3.0 / size) * 0.5 + 0.5)
        c = (c0[0] * v, c0[1] * v, c0[2] * v)
        if moss and n.z > 0.55 and noise.noise(co * 1.5 / size + Vector((seed, 0, 0))) > -0.1:
            c = mix(c, mossc, smoothstep(0.55, 0.85, n.z))
        return (clamp(c[0]), clamp(c[1]), clamp(c[2]), 0.0)
    paint(ob, fn)
    return ob


def tree_broadleaf(name, seed):
    random.seed(seed)
    H = random.uniform(9, 13)
    nodes, edges, radii = [(0, 0, -0.3), (0, 0, H * 0.45)], [(0, 1)], [0.45, 0.3]
    tips = []

    def branch(pi, d, length, r, depth):
        base = Vector(nodes[pi])
        tip = base + d * length
        nodes.append(tuple(tip))
        radii.append(r)
        edges.append((pi, len(nodes) - 1))
        ci = len(nodes) - 1
        if depth == 0:
            tips.append(tip)
            return
        for k in range(3 if depth > 1 else 2):
            a = random.uniform(0, TAU)
            nd = (d + Vector((math.cos(a), math.sin(a), 0)) * random.uniform(0.6, 1.0) + Vector((0, 0, 0.35))).normalized()
            branch(ci, nd, length * random.uniform(0.55, 0.7), r * 0.6, depth - 1)
    branch(1, Vector((0, 0, 1)), H * 0.25, 0.22, 3)
    trunk = skin_object('trunk', nodes, edges, radii, subdiv=1, branch=0.8)
    bark = hexcol('#4a3a2c')
    paint(trunk, lambda co, n: (bark[0] * (0.8 + 0.3 * noise.noise(co * 3)), bark[1], bark[2], 0.0))
    parts = [trunk]
    leaf = hexcol('#3f6b2a')
    for tip in tips:
        for k in range(2):
            c = tip + Vector((random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-0.3, 0.8)))
            s = random.uniform(1.4, 2.2)
            b = uv_sphere('leafball', c, s, seg=10, rings=7)
            displace(b, s * 0.45, s * 0.35, 'CLOUDS', levels=1)
            paint(b, lambda co, n: (clamp(leaf[0] * (0.7 + 0.5 * (n.z * 0.5 + 0.5))), clamp(leaf[1] * (0.75 + 0.5 * (n.z * 0.5 + 0.5))),
                                    clamp(leaf[2] * (0.7 + 0.3 * (n.z * 0.5 + 0.5))), clamp((co.z - H * 0.4) / H)))
            parts.append(b)
    return join(parts, name)


def tree_pine(name, seed):
    random.seed(seed)
    H = random.uniform(12, 18)
    trunk = chain([(0, 0, -0.3), (0, 0, H * 0.5), (0, 0, H)], [0.35, 0.22, 0.04], 'trunk', subdiv=1)
    bark = hexcol('#43352a')
    paint(trunk, lambda co, n: (*bark, 0.0))
    parts = [trunk]
    col = hexcol('#2c4a2a')
    layers = 7
    for i in range(layers):
        t = i / layers
        z = H * (0.22 + 0.72 * t)
        r = (1 - t) * H * 0.22 + 0.6
        c = chain([(0, 0, z), (0, 0, z + H * 0.16)], [r, 0.05], 'cone', subdiv=1)
        displace(c, 0.25, 0.6, 'CLOUDS', levels=1)
        v = 0.8 + 0.4 * t
        paint(c, lambda co, n, v=v: (clamp(col[0] * v), clamp(col[1] * v), clamp(col[2] * v), clamp(co.z / H)))
        parts.append(c)
    return join(parts, name)


def bush(name, seed):
    random.seed(seed)
    parts = []
    col = hexcol('#4a7030')
    for k in range(5):
        c = Vector((random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6), random.uniform(0.4, 0.9)))
        s = random.uniform(0.5, 0.8)
        b = uv_sphere('b', c, s, seg=10, rings=7)
        displace(b, s * 0.4, s * 0.3, 'CLOUDS', levels=1)
        paint(b, lambda co, n: (clamp(col[0] * (0.7 + 0.4 * n.z)), clamp(col[1] * (0.7 + 0.4 * n.z)), col[2], clamp(co.z)))
        parts.append(b)
    return join(parts, name)


def grass_clump(name, seed, blades=45, h=0.55, flowers=None):
    import bmesh
    random.seed(seed)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    cl = bm.loops.layers.color.new("Col")
    base_c, tip_c = hexcol('#3d5e22'), hexcol('#a3b65a')
    for b in range(blades):
        a = random.uniform(0, TAU)
        r = random.uniform(0, 0.35)
        x0, y0 = math.cos(a) * r, math.sin(a) * r
        hh = h * random.uniform(0.6, 1.2)
        w = 0.025 * random.uniform(0.7, 1.3)
        lean = Vector((math.cos(a), math.sin(a), 0)) * random.uniform(0.05, 0.25)
        rot = random.uniform(0, TAU)
        side = Vector((math.cos(rot), math.sin(rot), 0)) * w
        seg = 4
        rows = []
        for s in range(seg + 1):
            t = s / seg
            c = Vector((x0, y0, 0)) + lean * (t * t) * hh * 2 + Vector((0, 0, hh * t))
            ww = side * (1 - t)
            rows.append((bm.verts.new(c - ww), bm.verts.new(c + ww + side * 0.001), t))
        for s in range(seg):
            f = bm.faces.new((rows[s][0], rows[s][1], rows[s + 1][1], rows[s + 1][0]))
            for loop in f.loops:
                t = rows[s][2] if loop.vert in (rows[s][0], rows[s][1]) else rows[s + 1][2]
                c = mix(base_c, tip_c, t)
                loop[cl] = (*c, t)
    if flowers:
        fc = hexcol(flowers)
        for k in range(6):
            a = random.uniform(0, TAU)
            r = random.uniform(0, 0.3)
            ctr = Vector((math.cos(a) * r, math.sin(a) * r, h * random.uniform(0.7, 1.1)))
            ring = []
            for j in range(5):
                aa = TAU * j / 5
                ring.append(bm.verts.new(ctr + Vector((math.cos(aa) * 0.05, math.sin(aa) * 0.05, 0.01))))
            cv = bm.verts.new(ctr)
            for j in range(5):
                f = bm.faces.new((cv, ring[j], ring[(j + 1) % 5]))
                for loop in f.loops:
                    loop[cl] = (*fc, 1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    # convertit en attribut de couleur sRGB "Col"
    return ob


def shrine(name):
    parts = []
    base = chain([(0, 0, 0), (0, 0, 0.5)], [2.2, 2.0], 'base', subdiv=1)
    solid_paint(base, hexcol('#9a958a'), 0.0)
    parts.append(base)
    for i in range(6):
        a = TAU * i / 6
        p = Vector((math.cos(a) * 1.7, math.sin(a) * 1.7, 0.4))
        pil = chain([p, p + Vector((0, 0, 2.6))], [0.18, 0.13], 'pillar', subdiv=1)
        solid_paint(pil, hexcol('#b8b2a4'), 0.0)
        parts.append(pil)
    cr = cone('crystal', (0, 0, 0.9), (0, 0, 3.6), 0.45, 0.01, n=3, subdiv=1)
    solid_paint(cr, hexcol('#7fe8ff'), 6.0, jitter=0.0)
    parts.append(cr)
    return join(parts, name)


def export_static(ob, out_dir, name, preview_dir=None):
    folder = os.path.join(out_dir, 'Environment')
    os.makedirs(folder, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    ob.name = name
    path = os.path.join(folder, name + '.fbx')
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH'}, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', mesh_smooth_type='FACE', colors_type='SRGB',
                             bake_anim=False)
    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    print("[OK] %-16s static %6d tris -> %s" % (name, tris, path))
    if preview_dir:
        render_preview(ob, os.path.join(preview_dir, name + '.png'), env=True)


ENV = [
    ('SM_Rock_A', lambda: rock('r', 1.2, 1)),
    ('SM_Rock_B', lambda: rock('r', 0.8, 7, flat=0.7)),
    ('SM_Boulder', lambda: rock('r', 4.0, 13, flat=0.9)),
    ('SM_Cliff', lambda: rock('r', 9.0, 21, flat=1.6, moss=False, base='#7d776c')),
    ('SM_Tree_Broadleaf_A', lambda: tree_broadleaf('t', 3)),
    ('SM_Tree_Broadleaf_B', lambda: tree_broadleaf('t', 11)),
    ('SM_Tree_Pine_A', lambda: tree_pine('p', 5)),
    ('SM_Tree_Pine_B', lambda: tree_pine('p', 17)),
    ('SM_Bush', lambda: bush('b', 2)),
    ('SM_Grass', lambda: grass_clump('g', 4)),
    ('SM_Grass_Flowers', lambda: grass_clump('g', 9, blades=35, flowers='#f2e35a')),
    ('SM_Grass_FlowersPink', lambda: grass_clump('g', 12, blades=35, flowers='#e87ab0')),
    ('SM_Shrine', lambda: shrine('s')),
]


# ---------------------------------------------------------------------------
# Rendu de previsualisation (Cycles CPU)
# ---------------------------------------------------------------------------

def preview_material():
    mat = bpy.data.materials.new("VC")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Emission Color"])
    mathn = nt.nodes.new("ShaderNodeMath")
    mathn.operation = 'MULTIPLY'
    mathn.inputs[1].default_value = 2.0
    nt.links.new(attr.outputs["Alpha"], mathn.inputs[0])
    nt.links.new(mathn.outputs[0], bsdf.inputs["Emission Strength"])
    bsdf.inputs["Roughness"].default_value = 0.55
    return mat


def render_preview(ob, path, env=False):
    sc = bpy.context.scene
    ob.data.materials.clear()
    ob.data.materials.append(preview_material())
    if ob.data.color_attributes.get("Col") is None:
        pass
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 512
    sc.render.resolution_y = 512
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = 'AgX'
    except TypeError:
        sc.view_settings.view_transform = 'Filmic'
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.55, 0.68, 0.85, 1)
    bg.inputs[1].default_value = 0.8
    sc.world = world
    # sol
    me = bpy.data.meshes.new("ground")
    s = 200
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new("ground", me)
    link(g)
    gm = bpy.data.materials.new("G")
    gm.use_nodes = True
    gm.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (0.42, 0.45, 0.36, 1)
    me.materials.append(gm)
    sun_d = bpy.data.lights.new("sun", 'SUN')
    sun_d.energy = 3.5
    sun_d.angle = math.radians(4)
    sun = bpy.data.objects.new("sun", sun_d)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    link(sun)
    # cadrage
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    pts = [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (mn + mx) / 2
    size = (mx - mn).length
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 50
    cam = bpy.data.objects.new("cam", cam_d)
    link(cam)
    direction = Vector((-0.85, -1.3, 0.55)).normalized()
    cam.location = ctr + direction * size * 1.55
    cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = cam
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def contact_sheet(preview_dir, names, out_name, cols=6):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    ims = [(n, Image.open(os.path.join(preview_dir, n + '.png')).convert('RGB').resize((256, 256)))
           for n in names if os.path.exists(os.path.join(preview_dir, n + '.png'))]
    if not ims:
        return
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * 256, rows * 280), (24, 26, 32))
    d = ImageDraw.Draw(sheet)
    for i, (n, im) in enumerate(ims):
        x, y = (i % cols) * 256, (i // cols) * 280
        sheet.paste(im, (x, y))
        d.text((x + 8, y + 260), n, fill=(230, 230, 230))
    sheet.save(os.path.join(preview_dir, out_name))


# ---------------------------------------------------------------------------

def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(here, '..', '..', 'Art'))
    ap.add_argument('--previews', default=os.path.join(here, '..', '..', 'Docs', 'previews'))
    ap.add_argument('--only', default='')
    ap.add_argument('--no-render', action='store_true')
    a = ap.parse_args(argv)
    only = set(x.strip().lower() for x in a.only.split(',') if x.strip())
    prev = None if a.no_render else os.path.abspath(a.previews)
    if prev:
        os.makedirs(prev, exist_ok=True)
    out = os.path.abspath(a.out)
    for spec in CREATURES + [TAMER]:
        if only and spec['name'].lower() not in only:
            continue
        build_character(spec, out, prev)
    for name, fn in ENV:
        if only and name.lower() not in only:
            continue
        reset_scene()
        ob = fn()
        export_static(ob, out, name, prev)
    if prev:
        contact_sheet(prev, [c['name'] for c in CREATURES] + ['Tamer'], 'creatures_sheet.png')
        contact_sheet(prev, [e[0] for e in ENV], 'environment_sheet.png', cols=5)


if __name__ == '__main__':
    main()
