"""AETHERWILD - Scene de reference 'Prairie du Lac' (direction artistique de la carte, rendu Cycles)."""
import sys, os, math, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import bpy, bmesh
import numpy as np
from mathutils import Vector, Matrix, noise, Euler
from hero_common import *
import hero_braisillon as fox
import generate_assets as ga

OUT = os.path.join(HERE, "..", "..", "Docs", "previews", "v2")
TMP = os.environ.get("AETHER_TMP", "/tmp")

def leaf_texture(path, palette, seed, petals=False):
    from PIL import Image, ImageDraw
    rnd = random.Random(seed)
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for k in range(70 if petals else 45):
        cx, cy = rnd.uniform(60, 452), rnd.uniform(60, 452)
        L = rnd.uniform(28, 60) * (0.6 if petals else 1); W = L * (0.75 if petals else 0.42)
        a = rnd.uniform(0, math.tau)
        pts = []
        for i in range(24):
            t = i / 24 * math.tau
            px, py = math.cos(t) * L, math.sin(t) * W * (1 - 0.3 * math.cos(t))
            pts.append((cx + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a)))
        c = palette[rnd.randrange(len(palette))]
        v = rnd.uniform(0.8, 1.15)
        d.polygon(pts, fill=(int(min(255, c[0] * v)), int(min(255, c[1] * v)), int(min(255, c[2] * v)), 255))
    im.save(path)
    return path

def card_material(name, tex, translucency=0.35, rough=0.55):
    m = bpy.data.materials.new(name); m.use_nodes = True
    N = m.node_tree.nodes; L = m.node_tree.links
    b = N["Principled BSDF"]; b.inputs["Roughness"].default_value = rough
    img = N.new("ShaderNodeTexImage"); img.image = bpy.data.images.load(tex)
    L.new(img.outputs["Color"], b.inputs["Base Color"]); L.new(img.outputs["Alpha"], b.inputs["Alpha"])
    tr = N.new("ShaderNodeBsdfTranslucent"); L.new(img.outputs["Color"], tr.inputs["Color"])
    mx = N.new("ShaderNodeMixShader"); mx.inputs[0].default_value = translucency
    out = N["Material Output"]
    L.new(b.outputs[0], mx.inputs[1]); L.new(tr.outputs[0], mx.inputs[2])
    # le melange doit garder la transparence : on multiplie par l'alpha via un Transparent
    tp = N.new("ShaderNodeBsdfTransparent"); mx2 = N.new("ShaderNodeMixShader")
    L.new(img.outputs["Alpha"], mx2.inputs[0]); L.new(tp.outputs[0], mx2.inputs[1]); L.new(mx.outputs[0], mx2.inputs[2])
    L.new(mx2.outputs[0], out.inputs["Surface"])
    return m

def terrain():
    nx, ny = 260, 320
    xs = np.linspace(-220, 220, nx); ys = np.linspace(-30, 520, ny)
    X, Y = np.meshgrid(xs, ys)
    H = np.zeros_like(X)
    for i in range(ny):
        for j in range(nx):
            x, y = X[i, j], Y[i, j]
            n1 = noise.noise(Vector((x / 40, y / 40, 0.3)))
            n2 = noise.noise(Vector((x / 9, y / 9, 1.7)))
            h = 0.9 * n1 + 0.25 * n2 + 0.8
            shore = 72 + 10 * noise.noise(Vector((x / 35, 0.5, 2.0)))
            far = 175 + 12 * noise.noise(Vector((x / 40, 1.5, 3.0)))
            if y > shore:
                h -= sstep(shore, shore + 12, y) * 5 * (1 - sstep(far - 10, far, y))
            if y > far - 10:
                h += sstep(far - 10, far + 40, y) * (6 + 10 * (n1 * 0.5 + 0.5))
            if y > 260:
                r = 1 - abs(noise.noise(Vector((x / 70, y / 70, 5.0))))
                h += sstep(260, 420, y) * (60 + 130 * r * r) + 18 * n2 * sstep(260, 400, y)
            h += 2.5 * sstep(30, 140, abs(x)) * sstep(60, 0, y)   # petites collines laterales
            H[i, j] = h
    me = bpy.data.meshes.new("terrain")
    verts = np.stack([X.ravel(), Y.ravel(), H.ravel()], 1)
    idx = np.arange(nx * ny).reshape(ny, nx)
    faces = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1)
    me.from_pydata(verts.tolist(), [], faces.tolist()); me.update()
    for p in me.polygons: p.use_smooth = True
    ob = link(bpy.data.objects.new("terrain", me))
    # couleurs : herbe chaude, roche, neige
    def col(co, n):
        x, y, z = co
        g = mix(hexc("#4f7d1f"), hexc("#86a23a"), 0.5 + 0.5 * noise.noise(Vector((x / 15, y / 15, 0))))
        g = mix(g, hexc("#a8a04a"), sstep(0.2, 0.6, noise.noise(Vector((x / 50, y / 50, 4)))) * 0.5)
        c = mix(g, hexc("#6e6a62"), sstep(0.82, 0.62, n.z))
        c = mix(c, hexc("#d8c79c"), sstep(1.2, 0.2, z) * sstep(50, 70, y))
        c = mix(c, hexc("#eef2f6"), sstep(110, 140, z + 20 * noise.noise(Vector((x / 30, y / 30, 9)))) * sstep(0.4, 0.7, n.z))
        return (*c[:3], 1.0)
    paint(ob, col)
    m = bpy.data.materials.new("terrain"); m.use_nodes = True
    N = m.node_tree.nodes; b = N["Principled BSDF"]; vc = N.new("ShaderNodeVertexColor"); vc.layer_name = "Col"
    m.node_tree.links.new(vc.outputs[0], b.inputs["Base Color"]); b.inputs["Roughness"].default_value = 0.9
    ob.data.materials.append(m)
    # densite d'herbe : forte pres de la camera, nulle dans l'eau/montagne
    vg = ob.vertex_groups.new(name="grass")
    vgf = ob.vertex_groups.new(name="flowers")
    for v in ob.data.vertices:
        x, y, z = v.co
        d = math.hypot(x - 2, y - 2)
        w = math.exp(-d / 22) * (1 if z > 0.4 else 0) * (1 if y < 80 else 0)
        if w > 0.002: vg.add([v.index], w, 'REPLACE')
        wf = w * max(0, noise.noise(Vector((x / 6, y / 6, 7))) + 0.2)
        if wf > 0.002: vgf.add([v.index], min(1, wf), 'REPLACE')
    return ob

def grass_collection(name, flowers=None, seed=1, blades=45, h=0.55):
    coll = bpy.data.collections.new(name)
    mat = bpy.data.materials.new(name + "_m"); mat.use_nodes = True
    N = mat.node_tree.nodes; L = mat.node_tree.links; b = N["Principled BSDF"]
    vc = N.new("ShaderNodeVertexColor"); vc.layer_name = "Col"
    L.new(vc.outputs[0], b.inputs["Base Color"]); b.inputs["Roughness"].default_value = 0.6
    tr = N.new("ShaderNodeBsdfTranslucent"); L.new(vc.outputs[0], tr.inputs["Color"])
    mx = N.new("ShaderNodeMixShader"); mx.inputs[0].default_value = 0.3
    L.new(b.outputs[0], mx.inputs[1]); L.new(tr.outputs[0], mx.inputs[2]); L.new(mx.outputs[0], N["Material Output"].inputs["Surface"])
    for k in range(4):
        ob = ga.grass_clump(name + str(k), seed + k * 13, blades=blades, h=h, flowers=flowers)
        ob.data.materials.append(mat)
        ob.rotation_euler = (0, 0, k * math.pi / 2.7)
        bpy.context.scene.collection.objects.unlink(ob); coll.objects.link(ob)
        ob.location = (0, 0, -1000)
    bpy.context.scene.collection.children.link(coll)
    coll.hide_render = False
    return coll

def scatter(ob, coll, count, group, size=1.0, rnd=0.45, seed=0):
    ps = ob.modifiers.new(coll.name, 'PARTICLE_SYSTEM').particle_system
    st = ps.settings; ps.seed = seed
    st.type = 'EMITTER'; st.count = count; st.frame_start = 1; st.frame_end = 1; st.lifetime = 5000
    st.emit_from = 'FACE'; st.distribution = 'RAND'; st.physics_type = 'NO'
    st.render_type = 'COLLECTION'; st.instance_collection = coll; st.use_collection_pick_random = True
    st.particle_size = size; st.size_random = rnd
    st.use_rotations = True; st.rotation_mode = 'NONE'
    ps.vertex_group_density = group
    return ps

def tree(loc, seed, leaf_tex_mats, height=11.0, scale=1.0):
    random.seed(seed)
    nodes, edges, radii = [(0, 0, -0.5), (0, 0, height * 0.42)], [(0, 1)], [0.55, 0.4]
    tips = []
    def branch(pi, d, L, r, depth):
        base = Vector(nodes[pi]); tip = base + d * L
        nodes.append(tuple(tip)); radii.append(r); edges.append((pi, len(nodes) - 1)); ci = len(nodes) - 1
        if depth == 0: tips.append(tip); return
        for k in range(3):
            a = random.uniform(0, math.tau)
            nd = (d + Vector((math.cos(a), math.sin(a), 0)) * random.uniform(0.7, 1.1) + Vector((0, 0, 0.2))).normalized()
            branch(ci, nd, L * random.uniform(0.6, 0.75), r * 0.58, depth - 1)
    for k in range(3):
        a = k * math.tau / 3 + random.uniform(-0.4, 0.4)
        branch(1, Vector((math.cos(a), math.sin(a), 1.1)).normalized(), height * 0.3, 0.26, 3)
    trunk = ga.skin_object("trunk", nodes, edges, radii, subdiv=2, branch=0.8)
    bark = bpy.data.materials.new("bark"); bark.use_nodes = True
    N = bark.node_tree.nodes; L = bark.node_tree.links; b = N["Principled BSDF"]
    b.inputs["Base Color"].default_value = hexc("#5a3b2a"); b.inputs["Roughness"].default_value = 0.8
    vt = N.new("ShaderNodeTexVoronoi"); vt.inputs["Scale"].default_value = 9
    mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (3, 3, 0.6); tc = N.new("ShaderNodeTexCoord")
    L.new(tc.outputs["Object"], mp.inputs[0]); L.new(mp.outputs[0], vt.inputs["Vector"])
    bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.8
    L.new(vt.outputs["Distance"], bp.inputs["Height"]); L.new(bp.outputs[0], b.inputs["Normal"])
    trunk.data.materials.append(bark)
    trunk.location = loc; trunk.scale = (scale,) * 3
    # volumes de feuillage invisibles qui emettent des cartes de feuilles
    for i, tp in enumerate(tips):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=random.uniform(1.6, 2.4), location=Vector(loc) + tp * scale)
        em = bpy.context.object; em.scale = (1.2, 1.2, 0.8)
        mat = leaf_tex_mats[i % len(leaf_tex_mats)]
        bpy.ops.mesh.primitive_plane_add(size=0.9); card = bpy.context.object; card.data.materials.append(mat)
        card.location = (0, 0, -1000)
        ps = em.modifiers.new("leaves", 'PARTICLE_SYSTEM').particle_system; st = ps.settings
        st.type = 'EMITTER'; st.count = 700; st.frame_start = st.frame_end = 1; st.lifetime = 5000
        st.emit_from = 'VOLUME'; st.physics_type = 'NO'; st.render_type = 'OBJECT'; st.instance_object = card
        st.particle_size = 1.0; st.size_random = 0.4; st.use_rotations = True; st.rotation_mode = 'NONE'
        st.rotation_factor_random = 1.0
        em.show_instancer_for_render = False; em.show_instancer_for_viewport = False
    return trunk

def water():
    bpy.ops.mesh.primitive_plane_add(size=1200, location=(0, 300, -0.15))
    w = bpy.context.object
    m = bpy.data.materials.new("water"); m.use_nodes = True
    N = m.node_tree.nodes; L = m.node_tree.links; b = N["Principled BSDF"]
    b.inputs["Base Color"].default_value = hexc("#0b3b4a"); b.inputs["Roughness"].default_value = 0.02
    b.inputs["Transmission Weight"].default_value = 0.85; b.inputs["IOR"].default_value = 1.33
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 0.7; nz.inputs["Detail"].default_value = 6
    mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1, 3, 1); tc = N.new("ShaderNodeTexCoord")
    L.new(tc.outputs["Object"], mp.inputs[0]); L.new(mp.outputs[0], nz.inputs["Vector"])
    bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.12
    L.new(nz.outputs["Fac"], bp.inputs["Height"]); L.new(bp.outputs[0], b.inputs["Normal"])
    w.data.materials.append(m)

def shrine_obj(loc):
    s = ga.shrine("shrine")
    m = bpy.data.materials.new("stone"); m.use_nodes = True
    N = m.node_tree.nodes; b = N["Principled BSDF"]; vc = N.new("ShaderNodeVertexColor"); vc.layer_name = "Col"
    m.node_tree.links.new(vc.outputs[0], b.inputs["Base Color"]); m.node_tree.links.new(vc.outputs[0], b.inputs["Emission Color"])
    vca = N.new("ShaderNodeMath"); vca.operation = 'MULTIPLY'; vca.inputs[1].default_value = 12
    m.node_tree.links.new(vc.outputs["Alpha"], vca.inputs[0]); m.node_tree.links.new(vca.outputs[0], b.inputs["Emission Strength"])
    s.data.materials.append(m); s.location = loc
    l = bpy.data.lights.new("crystal", 'POINT'); l.energy = 2500; l.color = (0.4, 0.9, 1.0)
    lo = link(bpy.data.objects.new("crystal", l)); lo.location = Vector(loc) + Vector((0, 0, 3))

def main(res_x=1600, res_y=900, samples=64):
    body, parts, nose, eyes = fox.assemble()       # le renard (reinitialise la scene)
    rig = list(parts) + [nose] + eyes
    # on regroupe le renard sous un parent pour le placer dans la scene
    root = link(bpy.data.objects.new("fox_root", None))
    for o in rig: o.parent = root
    root.location = (1.6, 6.5, 0.55); root.rotation_euler = (0, 0, math.radians(-40)); root.scale = (1.6, 1.6, 1.6)
    ter = terrain()
    gA = grass_collection("grass", seed=3, blades=55, h=0.5)
    gF = grass_collection("flowersY", flowers="#f4d64a", seed=8, blades=35, h=0.45)
    gP = grass_collection("flowersP", flowers="#f09ac0", seed=11, blades=35, h=0.45)
    scatter(ter, gA, 260000, "grass", size=1.0, seed=1)
    scatter(ter, gF, 25000, "flowers", size=0.9, seed=2)
    scatter(ter, gP, 25000, "flowers", size=0.9, seed=3)
    green = leaf_texture(os.path.join(TMP, "leaf_green.png"), [(70, 120, 35), (95, 145, 45), (60, 100, 30)], 1)
    pink = leaf_texture(os.path.join(TMP, "leaf_pink.png"), [(246, 196, 214), (240, 170, 200), (252, 225, 235)], 2, petals=True)
    mg, mp = card_material("leafG", green), card_material("leafP", pink, translucency=0.45)
    tree((-9, 22, 0.6), 4, [mp, mp, mg]); tree((14, 38, 0.6), 9, [mg]); tree((-26, 48, 0.8), 13, [mp, mg], height=9)
    tree((30, 60, 0.6), 21, [mg], height=13)
    water(); shrine_obj((-6, 58, 0.5))
    # ciel + soleil dore
    sc = bpy.context.scene
    w = bpy.data.worlds.new("sky"); w.use_nodes = True; sc.world = w
    sky = w.node_tree.nodes.new("ShaderNodeTexSky")
    try:
        sky.sun_elevation = math.radians(16); sky.sun_rotation = math.radians(150)
    except Exception: pass
    w.node_tree.links.new(sky.outputs[0], w.node_tree.nodes["Background"].inputs[0])
    sun = link(bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN')))
    sun.data.energy = 4.5; sun.data.angle = math.radians(1.0); sun.data.color = (1.0, 0.86, 0.68)
    sun.rotation_euler = (math.radians(74), 0, math.radians(150))
    # brume atmospherique (volume borne)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 250, 60)); haze = bpy.context.object; haze.scale = (900, 900, 160)
    hm = bpy.data.materials.new("haze"); hm.use_nodes = True; hn = hm.node_tree.nodes
    hn.remove(hn["Principled BSDF"]); vol = hn.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = 0.0016; vol.inputs["Color"].default_value = (0.85, 0.88, 0.95, 1)
    hm.node_tree.links.new(vol.outputs[0], hn["Material Output"].inputs["Volume"]); haze.data.materials.append(hm)
    # camera basse, a hauteur d'explorateur
    cam = link(bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))); cam.data.lens = 30
    cam.location = (0.0, -1.5, 1.45)
    cam.rotation_euler = (Vector((4, 40, 3.5)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.dof.use_dof = True; cam.data.dof.focus_distance = 9.0; cam.data.dof.aperture_fstop = 4.0
    sc.camera = cam
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = samples; sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6; sc.cycles.transparent_max_bounces = 24
    sc.render.resolution_x, sc.render.resolution_y = res_x, res_y
    sc.view_settings.view_transform = 'AgX'
    try: sc.view_settings.look = 'AgX - Punchy'
    except Exception: pass
    sc.view_settings.exposure = -2.6
    os.makedirs(OUT, exist_ok=True)
    sc.render.filepath = os.path.join(OUT, "Concept_PrairieDuLac.png")
    bpy.ops.render.render(write_still=True)

if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if args and args[0] == "preview": main(800, 450, 24)
    else: main()
