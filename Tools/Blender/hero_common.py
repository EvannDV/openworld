"""Outils communs aux modeles 'hero' (v2) : sculpture par metaballs, yeux, rendu studio."""
import bpy, bmesh, math, random
from mathutils import Vector, Quaternion, Matrix, noise

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 30

def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob

def hexc(h, a=1.0):
    h = h.lstrip('#')
    c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (*c, a)

class Sculpt:
    """Accumule des primitives metaball (ellipsoides / capsules) puis les convertit en maillage propre."""
    def __init__(self, name, res=0.006, threshold=0.6):
        self.mb = bpy.data.metaballs.new(name)
        self.mb.resolution = res
        self.mb.render_resolution = res
        self.mb.threshold = threshold
        self.ob = link(bpy.data.objects.new(name, self.mb))

    def ell(self, co, r, size=(1, 1, 1), rot=None, stiff=2.0, neg=False):
        e = self.mb.elements.new(type='ELLIPSOID')
        e.co = co; e.radius = r; e.stiffness = stiff
        e.size_x, e.size_y, e.size_z = size
        if rot is not None: e.rotation = rot
        e.use_negative = neg
        return e

    def capsule(self, a, b, r, stiff=2.0):
        a, b = Vector(a), Vector(b)
        e = self.mb.elements.new(type='CAPSULE')
        e.co = (a + b) / 2; e.radius = r; e.stiffness = stiff
        e.size_x = (b - a).length / 2
        e.rotation = Vector((1, 0, 0)).rotation_difference((b - a).normalized())
        return e

    def chain(self, pts, radii, stiff=2.0):
        for i in range(len(pts) - 1):
            self.capsule(pts[i], pts[i + 1], (radii[i] + radii[i + 1]) / 2, stiff)

    def to_mesh(self, voxel=0.0035, smooth_iter=6, target_tris=80000):
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(self.ob.evaluated_get(dg))
        ob = link(bpy.data.objects.new(self.ob.name + "_mesh", me))
        bpy.data.objects.remove(self.ob)
        m = ob.modifiers.new("remesh", 'REMESH'); m.mode = 'VOXEL'; m.voxel_size = voxel; m.use_smooth_shade = True
        s = ob.modifiers.new("smooth", 'SMOOTH'); s.factor = 0.6; s.iterations = smooth_iter
        apply_all(ob)
        tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
        if tris > target_tris:
            d = ob.modifiers.new("dec", 'DECIMATE'); d.ratio = target_tris / tris
            apply_all(ob)
        for p in ob.data.polygons: p.use_smooth = True
        return ob

def apply_all(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data; ob.modifiers.clear(); ob.data = me; bpy.data.meshes.remove(old)
    for p in me.polygons: p.use_smooth = True
    return ob

def paint(ob, fn, name="Col"):
    me = ob.data
    attr = me.color_attributes.get(name) or me.color_attributes.new(name, 'FLOAT_COLOR', 'POINT')
    for i, v in enumerate(me.vertices):
        attr.data[i].color = fn(v.co, v.normal)

def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(len(a)))

def sstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0))); return t * t * (3 - 2 * t)

# ---------------------------------------------------------------- materiaux
def fur_material(name, sheen=0.6, rough=0.62, sss=0.08, bump=0.25, strand_scale=180.0):
    """Peau/fourrure stylisee-realiste : couleur de sommet + brins (bump directionnel) + sheen velours."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    b = N["Principled BSDF"]
    col = N.new("ShaderNodeVertexColor"); col.layer_name = "Col"
    L.new(col.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    for k, v in (("Sheen Weight", sheen), ("Sheen Roughness", 0.35), ("Subsurface Weight", sss)):
        if k in b.inputs: b.inputs[k].default_value = v
    if "Subsurface Radius" in b.inputs: b.inputs["Subsurface Radius"].default_value = (0.02, 0.008, 0.004)
    # brins de fourrure : ondes etirees + bruit, en coordonnees objet
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (strand_scale, strand_scale * 0.25, strand_scale)
    L.new(tc.outputs["Object"], mp.inputs["Vector"])
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 1.0; nz.inputs["Detail"].default_value = 8
    if "Distortion" in nz.inputs: nz.inputs["Distortion"].default_value = 0.4
    L.new(mp.outputs["Vector"], nz.inputs["Vector"])
    bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = bump; bp.inputs["Distance"].default_value = 0.002
    L.new(nz.outputs["Fac"], bp.inputs["Height"]); L.new(bp.outputs["Normal"], b.inputs["Normal"])
    # emission pilotee par l'alpha de la couleur de sommet
    if "Emission Color" in b.inputs:
        L.new(col.outputs["Color"], b.inputs["Emission Color"])
        mul = N.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = 25.0
        L.new(col.outputs["Alpha"], mul.inputs[0]); L.new(mul.outputs[0], b.inputs["Emission Strength"])
    return m

def simple_material(name, color, rough=0.4, metal=0.0, emit=0.0, coat=0.0, transmission=0.0, ior=1.45):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if "Coat Weight" in b.inputs: b.inputs["Coat Weight"].default_value = coat
    if "Transmission Weight" in b.inputs: b.inputs["Transmission Weight"].default_value = transmission
    b.inputs["IOR"].default_value = ior
    if emit > 0:
        b.inputs["Emission Color"].default_value = color
        b.inputs["Emission Strength"].default_value = emit
    return m

def iris_material(name, iris_hex, ring_hex="#2a1405"):
    """Iris procedural : degrade radial + stries + pupille, sur un disque oriente +Z local."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    b = N["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.25
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ"); L.new(tc.outputs["Object"], sep.inputs[0])
    # rayon dans le plan XY local
    mx = N.new("ShaderNodeMath"); mx.operation = 'MULTIPLY'; L.new(sep.outputs[0], mx.inputs[0]); L.new(sep.outputs[0], mx.inputs[1])
    my = N.new("ShaderNodeMath"); my.operation = 'MULTIPLY'; L.new(sep.outputs[1], my.inputs[0]); L.new(sep.outputs[1], my.inputs[1])
    ad = N.new("ShaderNodeMath"); ad.operation = 'ADD'; L.new(mx.outputs[0], ad.inputs[0]); L.new(my.outputs[0], ad.inputs[1])
    r = N.new("ShaderNodeMath"); r.operation = 'SQRT'; L.new(ad.outputs[0], r.inputs[0])
    ramp = N.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0; cr.elements[0].color = (0.003, 0.002, 0.002, 1)
    cr.elements[1].position = 1.0; cr.elements[1].color = hexc(ring_hex)
    e = cr.elements.new(0.36); e.color = (0.003, 0.002, 0.002, 1)
    e = cr.elements.new(0.42); e.color = hexc(iris_hex)
    e = cr.elements.new(0.80); e.color = tuple(min(1, c * 1.5) for c in hexc(iris_hex)[:3]) + (1,)
    e = cr.elements.new(0.93); e.color = hexc(ring_hex)
    sc = N.new("ShaderNodeMath"); sc.operation = 'DIVIDE'; sc.inputs[1].default_value = 1.0
    L.new(r.outputs[0], sc.inputs[0])
    L.new(sc.outputs[0], ramp.inputs[0])
    # stries radiales
    wave = N.new("ShaderNodeTexNoise"); wave.inputs["Scale"].default_value = 60
    L.new(tc.outputs["Object"], wave.inputs["Vector"])
    mixn = N.new("ShaderNodeMix"); mixn.data_type = 'RGBA'; mixn.blend_type = 'MULTIPLY'
    mixn.inputs["Factor"].default_value = 0.35
    L.new(ramp.outputs["Color"], mixn.inputs[6]); L.new(wave.outputs["Color"], mixn.inputs[7])
    L.new(mixn.outputs[2], b.inputs["Base Color"])
    if "Emission Color" in b.inputs:
        L.new(mixn.outputs[2], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = 0.6
    return m, r  # r : noeud rayon (pour l'echelle)

def eye_material(name, iris_hex, pupil_frac=0.45, iris_start=0.62):
    """Oeil complet sur UNE sphere : sclere, limbe sombre, iris degrade + stries, pupille (axe +Z local)."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    N = m.node_tree.nodes; L = m.node_tree.links
    b = N["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.05
    if "Coat Weight" in b.inputs: b.inputs["Coat Weight"].default_value = 1.0; b.inputs["Coat Roughness"].default_value = 0.02
    tc = N.new("ShaderNodeTexCoord")
    nrm = N.new("ShaderNodeVectorMath"); nrm.operation = 'NORMALIZE'; L.new(tc.outputs["Object"], nrm.inputs[0])
    sep = N.new("ShaderNodeSeparateXYZ"); L.new(nrm.outputs[0], sep.inputs[0])
    ramp = N.new("ShaderNodeValToRGB"); cr = ramp.color_ramp
    iris = hexc(iris_hex); bright = tuple(min(1, c * 1.8 + 0.05) for c in iris[:3]) + (1,)
    pz = 1 - (1 - iris_start) * pupil_frac
    stops = [(0.0, hexc("#efe8df")), (iris_start - 0.04, hexc("#e6ddd2")), (iris_start - 0.005, hexc("#140a05")),
             (iris_start + 0.03, tuple(c * 0.55 for c in iris[:3]) + (1,)), (iris_start + 0.16, iris),
             (pz - 0.03, bright), (pz, (0.004, 0.003, 0.003, 1)), (1.0, (0.002, 0.002, 0.002, 1))]
    cr.elements[0].position, cr.elements[0].color = stops[0]
    cr.elements[1].position, cr.elements[1].color = stops[-1]
    for pos, col in stops[1:-1]:
        e = cr.elements.new(pos); e.color = col
    L.new(sep.outputs[2], ramp.inputs[0])
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 35; L.new(tc.outputs["Object"], nz.inputs["Vector"])
    mx = N.new("ShaderNodeMix"); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.inputs["Factor"].default_value = 0.25
    L.new(ramp.outputs["Color"], mx.inputs[6]); L.new(nz.outputs["Color"], mx.inputs[7])
    L.new(mx.outputs[2], b.inputs["Base Color"])
    if "Emission Color" in b.inputs:
        L.new(mx.outputs[2], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = 0.25
    return m

def make_eye(center, radius, look_dir, iris_hex, name="eye", squash=(1.0, 1.0, 0.82), iris_start=0.62):
    look = Vector(look_dir).normalized()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=radius, location=center)
    e = bpy.context.object; e.name = name
    e.rotation_mode = 'QUATERNION'; e.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(look)
    e.scale = squash
    bpy.ops.object.shade_smooth()
    e.data.materials.append(eye_material(name + "_mat", iris_hex, iris_start=iris_start))
    return [e]

# ---------------------------------------------------------------- rendu
def studio(target, size, path, res=1400, samples=96, angle=(-0.9, -1.35, 0.45), lens=70, bg="#d9dadc", exposure=0.0):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x = res; sc.render.resolution_y = res
    try:
        sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Punchy'
    except Exception: pass
    sc.view_settings.exposure = exposure
    w = bpy.data.worlds.new("w"); w.use_nodes = True; sc.world = w
    w.node_tree.nodes["Background"].inputs[0].default_value = hexc(bg)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.15
    # sol cyclo
    bpy.ops.mesh.primitive_plane_add(size=size * 40, location=(0, 0, 0))
    fl = bpy.context.object
    fl.data.materials.append(simple_material("floor", hexc(bg), rough=0.85))
    def area(name, loc, energy, size_l, color=(1, 1, 1)):
        l = bpy.data.lights.new(name, 'AREA'); l.energy = energy; l.size = size_l; l.color = color
        o = link(bpy.data.objects.new(name, l)); o.location = loc
        o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    t = Vector(target)
    area("key", t + Vector((-1.6, -2.2, 2.4)) * size, 260 * size ** 2, 1.6 * size, (1.0, 0.95, 0.88))
    area("fill", t + Vector((2.4, -1.6, 0.9)) * size, 70 * size ** 2, 2.5 * size, (0.85, 0.9, 1.0))
    area("rim", t + Vector((0.6, 2.6, 1.9)) * size, 380 * size ** 2, 1.0 * size, (1.0, 0.92, 0.85))
    cam = link(bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))); cam.data.lens = lens
    cam.location = t + Vector(angle).normalized() * size * 4.3
    cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.dof.use_dof = True; cam.data.dof.focus_distance = (t - cam.location).length; cam.data.dof.aperture_fstop = 5.6
    sc.camera = cam
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
