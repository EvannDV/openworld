"""BRAISILLON v2 - renard de braise, style realiste-stylise (sculpte par metaballs)."""
import sys, os, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector, Quaternion, Euler, noise
from hero_common import *

def q(x=0, y=0, z=0):
    return Euler((math.radians(x), math.radians(y), math.radians(z))).to_quaternion()

def build():
    S = Sculpt("Braisillon", res=0.0045)
    S.ell((0, -0.09, 0.30), 0.17, (0.8, 0.85, 0.95), stiff=2.0)          # poitrail
    S.ell((0, 0.03, 0.30), 0.16, (0.72, 1.05, 0.8), stiff=2.0)           # ventre
    S.ell((0, 0.14, 0.31), 0.16, (0.85, 0.85, 0.9), stiff=2.0)           # croupe
    S.capsule((0, -0.12, 0.37), (0, -0.2, 0.45), 0.085)                  # cou
    S.ell((0, -0.24, 0.50), 0.19, (1.0, 0.92, 0.9), stiff=2.2)           # crane (grosse tete)
    for sx in (-1, 1):
        S.ell((sx * 0.095, -0.265, 0.445), 0.11, (1.0, 0.95, 0.85), stiff=2.0)   # joues duveteuses
    S.ell((0, -0.355, 0.455), 0.085, (0.85, 1.15, 0.72), q(-6, 0, 0), stiff=2.2)  # museau court
    S.ell((0, -0.405, 0.46), 0.045, (0.9, 1.0, 0.8), stiff=2.0)
    for sx in (-1, 1):
        x = sx * 0.072
        S.ell((x, -0.11, 0.25), 0.1, (0.7, 0.8, 1.1), stiff=2.0)                 # epaule
        S.chain([(x, -0.115, 0.22), (x, -0.125, 0.12), (x, -0.13, 0.05)], [0.05, 0.043, 0.04])
        S.ell((x, -0.15, 0.03), 0.06, (0.85, 1.15, 0.6), stiff=2.0)              # patte ronde
    for sx in (-1, 1):
        x = sx * 0.08
        S.ell((x, 0.15, 0.27), 0.13, (0.7, 1.0, 1.1), q(12, 0, 0), stiff=2.0)    # cuisse
        S.chain([(x, 0.18, 0.18), (x, 0.17, 0.11), (x, 0.15, 0.05)], [0.048, 0.042, 0.04])
        S.ell((x, 0.13, 0.03), 0.06, (0.85, 1.15, 0.6), stiff=2.0)
    pts = []
    for i in range(11):
        t = i / 10
        pts.append(Vector((0.025 * math.sin(t * 2.5), 0.24 + 0.34 * t - 0.14 * t * t, 0.33 + 0.38 * t ** 1.2)))
        r = 0.06 + 0.12 * math.sin(math.pi * min(1.0, t * 1.0 + 0.08)) ** 0.7
        S.ell(pts[-1], r, (0.9, 1.1, 0.95), stiff=1.5)
    body = S.to_mesh(voxel=0.003, smooth_iter=10, target_tris=90000)
    body.name = "Braisillon_body"
    return body, pts

def surface_point(ob, origin, direction):
    """Point de la surface atteint depuis l'interieur (origin) vers direction."""
    d = Vector(direction).normalized()
    hit, loc, nrm, _ = ob.ray_cast(Vector(origin) + d * 0.6, -d)
    return (loc, nrm) if hit else (Vector(origin) + d * 0.15, d)

def color_fn(tail_pts):
    orange = hexc("#d2561c"); back = hexc("#9c3a12"); cream = hexc("#f4e6cf"); sock = hexc("#2b1a12")
    ember = hexc("#ffb33a"); root = Vector(tail_pts[0]); tip = Vector(tail_pts[-1])
    def fn(co, n):
        x, y, z = co
        c = mix(orange, back, sstep(0.2, 0.95, n.z) * 0.6)
        under = sstep(-0.15, -0.55, n.z) * sstep(0.36, 0.26, z)
        chest = sstep(-0.12, -0.2, y) * sstep(0.47, 0.40, z) * sstep(-0.1, -0.45, n.y)
        face = sstep(-0.27, -0.31, y) * sstep(0.495, 0.465, z)
        cheek = sstep(0.07, 0.13, abs(x)) * sstep(-0.2, -0.26, y) * sstep(0.49, 0.45, z) * sstep(0.3, 0.38, z)
        c = mix(c, cream, max(under, chest, face, cheek))
        if y > -0.3 or z < 0.2:
            c = mix(c, sock, sstep(0.13, 0.07, z))
        a = 0.0
        if y > 0.22 and z > 0.3:
            d = (Vector(co) - root).length / max(1e-3, (tip - root).length)
            c = mix(c, cream, sstep(0.66, 0.8, d))
            c = mix(c, ember, sstep(0.84, 0.98, d))
            a = sstep(0.86, 1.0, d) * 0.35
        v = 0.94 + 0.08 * noise.noise(Vector(co) * 45)
        return (c[0] * v, c[1] * v, c[2] * v, a)
    return fn

def tuft(base, direction, length, width, n=5, spread=0.5, seed=0):
    """Touffe de fourrure : plusieurs meches coniques courbees."""
    random.seed(seed)
    import bmesh
    me = bpy.data.meshes.new("tuft"); bm = bmesh.new()
    base = Vector(base); direction = Vector(direction).normalized()
    side = direction.cross(Vector((0, 0, 1)))
    if side.length < 1e-3: side = Vector((1, 0, 0))
    side.normalize(); up = side.cross(direction).normalized()
    for k in range(n):
        off = side * random.uniform(-spread, spread) * width + up * random.uniform(-spread, spread) * width * 0.5
        d = (direction + side * random.uniform(-0.35, 0.35) + up * random.uniform(-0.2, 0.3)).normalized()
        L = length * random.uniform(0.7, 1.1)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=width * random.uniform(0.55, 0.8), radius2=0.0005, depth=L,
                              matrix=Matrix.Translation(base + off + d * L / 2) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4())
    bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new("tuft", me))
    sd = ob.modifiers.new("s", 'SUBSURF'); sd.levels = 1
    apply_all(ob)
    return ob

def ear(side):
    """Oreille : coque concave a bord epais + interieur pelucheux."""
    import bmesh
    me = bpy.data.meshes.new("ear"); bm = bmesh.new()
    H, W = 0.15, 0.062
    rows, cols = 10, 9
    grid = []
    for i in range(rows + 1):
        t = i / rows
        w = W * (1 - t) ** 1.15 * (0.8 + 0.2 * math.sin(math.pi * min(1, t * 1.6)))
        row = []
        for j in range(cols + 1):
            u = j / cols * 2 - 1
            depth = -0.035 * (1 - u * u) * (1 - t) ** 0.6    # concavite
            row.append(bm.verts.new((u * w, depth, t * H)))
        grid.append(row)
    for i in range(rows):
        for j in range(cols):
            bm.faces.new((grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]))
    bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new("ear", me))
    so = ob.modifiers.new("sol", 'SOLIDIFY'); so.thickness = 0.012; so.offset = 1
    sd = ob.modifiers.new("sub", 'SUBSURF'); sd.levels = 2
    apply_all(ob)
    ob.rotation_euler = (math.radians(-12), math.radians(side * -24), math.radians(side * 14))
    ob.location = (side * 0.075, -0.25, 0.68)
    outer, inner, tip = hexc("#c8501d"), hexc("#f6dcc4"), hexc("#1d120c")
    def fn(co, n):
        t = co.z / 0.15
        wloc = 0.062 * max(0.05, (1 - t)) ** 1.15
        inside = sstep(-0.1, -0.5, n.y) * sstep(0.75, 0.5, abs(co.x) / wloc) * sstep(0.85, 0.55, t)
        c = mix(outer, inner, inside)
        c = mix(c, tip, sstep(0.72, 0.85, t))
        return (*c[:3], 0.0)
    paint(ob, fn)
    return ob

def add_fur(ob, mat, count=60000, length=0.022):
    ps = ob.modifiers.new("Fur", 'PARTICLE_SYSTEM').particle_system
    st = ps.settings
    st.type = 'HAIR'; st.count = count; st.hair_length = length
    st.use_advanced_hair = True
    st.child_type = 'INTERPOLATED'; st.child_percent = 4; st.rendered_child_count = 8
    st.clump_factor = 0.55; st.child_length = 0.9; st.roughness_endpoint = 0.004; st.roughness_2 = 0.003
    st.normal_factor = 0.55; st.tangent_factor = 0.0
    st.object_align_factor = (0.0, 0.35, -0.6)    # meches couchees vers l'arriere et le bas
    st.display_step = 3; st.render_step = 4
    st.root_radius = 0.0012; st.tip_radius = 0.0
    try:
        st.shape = 0.4
    except Exception:
        pass
    st.material = 1

def place_ear(ob, base, side):
    ob.rotation_euler = (math.radians(-8), math.radians(side * -22), math.radians(side * 18))
    ob.scale = (1.0, 1.0, 1.0)
    ob.location = base - Vector((0, 0, 0.02))

def assemble():
    reset()
    body, tail = build()
    paint(body, color_fn(tail))
    parts = [body]
    fur = fur_material("Braisillon_fur", sheen=0.9, rough=0.58, bump=0.6, strand_scale=140.0)
    head_c = Vector((0, -0.24, 0.50))
    for s in (-1, 1):
        e = ear(s)
        loc, _ = surface_point(body, head_c, (s * 0.75, 0.1, 0.85))
        loc.x = s * max(abs(loc.x), 0.1)
        place_ear(e, loc, s)
        parts.append(e)
    cream, orng = hexc("#f4e6cf"), hexc("#c24d18")
    specs = []
    for s in (-1, 1):
        loc, n = surface_point(body, Vector((s * 0.09, -0.27, 0.44)), (s, -0.2, -0.2))
        specs.append((loc - n * 0.025, (s * 0.8, 0.45, -0.6), 0.06, 0.05, 12, s + 10, hexc("#efd8bd")))
    loc, n = surface_point(body, Vector((0, -0.1, 0.32)), (0, -1, -0.3))
    specs.append((loc - n * 0.03, (0, -0.55, -1), 0.055, 0.07, 14, 3, cream))
    loc, n = surface_point(body, head_c, (0, -0.3, 1))
    specs.append((loc - n * 0.01, (0, -0.5, 0.7), 0.06, 0.035, 5, 4, orng))
    for base, d, L, w, k, seed, col in specs:
        t = tuft(base, d, L, w, k, spread=0.8, seed=seed)
        paint(t, lambda co, n, col=col: (*col[:3], 0.0))
        parts.append(t)
    # flamme de braise au bout de la queue
    tip = Vector(tail[-1]); prev = Vector(tail[-3])
    tdir = (tip - prev).normalized()
    loc, n = surface_point(body, tip, tdir + Vector((0, 0, 0.6)))
    t = tuft(loc - n * 0.035, tdir * 0.4 + Vector((0, 0, 1)), 0.13, 0.06, 11, spread=0.6, seed=5)
    paint(t, lambda co, n: (*mix(hexc("#ff7a1a"), hexc("#ffd36a"), sstep(loc.z, loc.z + 0.12, co.z))[:3], 0.1))
    parts.append(t)
    for p in parts:
        p.data.materials.clear(); p.data.materials.append(fur)
    # truffe
    loc, n = surface_point(body, Vector((0, -0.37, 0.465)), (0, -1, 0.25))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.026, location=loc - n * 0.006)
    nose = bpy.context.object; nose.scale = (1.3, 0.85, 0.8); bpy.ops.object.shade_smooth()
    nose.data.materials.append(simple_material("nose", hexc("#140d0b"), rough=0.22, coat=0.7))
    # grands yeux expressifs
    eyes = []
    for s in (-1, 1):
        d = Vector((s * 0.42, -1.0, 0.32)).normalized()
        loc, n = surface_point(body, head_c + Vector((0, 0, 0.02)), d)
        r = 0.043
        eyes += make_eye(loc - n * r * 0.45, r, (s * 0.3, -1.0, 0.06), "#ff8c1a", name="eye%d" % s, squash=(1.0, 1.0, 0.85))
    return body, parts, nose, eyes

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Docs", "previews", "v2"))
    ap.add_argument("--res", type=int, default=1400); ap.add_argument("--samples", type=int, default=96)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    os.makedirs(a.out, exist_ok=True)
    body, parts, nose, eyes = assemble()
    studio((0, -0.04, 0.36), 0.6, os.path.join(a.out, "Braisillon_v2.png"), res=a.res, samples=a.samples, angle=(-1.0, -1.3, 0.28), exposure=-0.35)
