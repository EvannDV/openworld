"""
AETHERWILD - Script d'installation dans l'editeur Unreal (Python)
================================================================
A lancer UNE FOIS dans l'editeur, apres avoir importe le terrain (Landscape) :
    Outils > Executer un script Python...  ->  Tools/Unreal/setup_aetherwild.py
ou dans la console Python de l'editeur :
    import setup_aetherwild; setup_aetherwild.run()

Ce que fait le script :
  1. Cree les materiaux : terrain procedural (herbe/roche/sable/neige/cendres selon
     altitude et pente), eau "Single Layer Water" avec vagues animees, vegetation
     au vent, creatures (couleurs + parties lumineuses), effets lumineux.
  2. Importe tous les FBX de Art/ (17 creatures + dresseur avec squelettes et
     animations, 13 assets d'environnement en Nanite) et leur assigne les materiaux.
  3. Configure le niveau ouvert : soleil + lune (cycle jour/nuit pilote en C++),
     ciel atmospherique, nuages volumetriques, brouillard volumetrique, Sky Light
     temps reel, post-process (Lumen haute qualite), materiau du Landscape, ocean.
  4. Sauvegarde le niveau sous /Game/Aetherwild/Maps/L_Aetherwild.

Le script est idempotent : on peut le relancer sans dupliquer les acteurs.
"""
import json
import os

import unreal

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ART = os.path.join(ROOT, "Art")
GAME = "/Game/Aetherwild"
MAT_DIR = GAME + "/Materials"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary


def log(msg):
    unreal.log("[Aetherwild] " + msg)


def warn(msg):
    unreal.log_warning("[Aetherwild] " + msg)


def setp(obj, name, value):
    """set_editor_property tolerant (les noms varient legerement selon les versions d'UE)."""
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as e:  # noqa
        warn("propriete %s ignoree sur %s (%s)" % (name, obj.get_class().get_name() if hasattr(obj, 'get_class') else obj, e))
        return False


def world_config():
    with open(os.path.join(ROOT, "Content", "Data", "world.json")) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Materiaux
# ---------------------------------------------------------------------------

def new_material(name):
    path = "%s/%s" % (MAT_DIR, name)
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    return asset_tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())


def expr(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        setp(e, k, v)
    return e


def scalar(mat, name, value, x, y):
    return expr(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value)


def vector(mat, name, color, x, y):
    return expr(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name, default_value=unreal.LinearColor(*color))


def custom(mat, code, inputs, out_type, x, y, desc="Custom"):
    c = expr(mat, unreal.MaterialExpressionCustom, x, y)
    setp(c, "code", code)
    setp(c, "description", desc)
    setp(c, "output_type", out_type)
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    setp(c, "inputs", ins)
    return c


def linear_vc(mat, x, y):
    """Couleur de sommet (sRGB venant de Blender) convertie en lineaire."""
    vc = expr(mat, unreal.MaterialExpressionVertexColor, x - 300, y)
    pw = expr(mat, unreal.MaterialExpressionPower, x, y, const_exponent=2.2)
    link(vc, "", pw, "Base")
    return vc, pw


def link(a, a_out, b, b_in):
    if not mel.connect_material_expressions(a, a_out, b, b_in):
        warn("connexion impossible %s.%s -> %s" % (a.get_name(), a_out, b_in))


def finish(mat):
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    log("materiau " + mat.get_name())
    return mat


def make_creature_material():
    m = new_material("M_CreatureVC")
    setp(m, "used_with_skeletal_mesh", True)
    setp(m, "used_with_instanced_static_meshes", True)
    vc, lin = linear_vc(m, -900, 0)
    tint = vector(m, "Tint", (1, 1, 1, 1), -900, 200)
    base = expr(m, unreal.MaterialExpressionMultiply, -600, 0)
    link(lin, "", base, "A")
    link(tint, "", base, "B")
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    glow = scalar(m, "GlowStrength", 14.0, -900, 400)
    e1 = expr(m, unreal.MaterialExpressionMultiply, -600, 250)
    link(base, "", e1, "A")
    link(vc, "A", e1, "B")
    e2 = expr(m, unreal.MaterialExpressionMultiply, -400, 300)
    link(e1, "", e2, "A")
    link(glow, "", e2, "B")
    mel.connect_material_property(e2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    rough = scalar(m, "Roughness", 0.6, -600, 500)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    spec = scalar(m, "Specular", 0.4, -600, 600)
    mel.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)
    # leger "fuzz" : assombrit les bords pour donner du volume au pelage
    fres = expr(m, unreal.MaterialExpressionFresnel, -900, 700)
    ao = expr(m, unreal.MaterialExpressionOneMinus, -600, 700)
    link(fres, "", ao, "")
    mel.connect_material_property(ao, "", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    return finish(m)


def make_foliage_material():
    m = new_material("M_FoliageVC")
    setp(m, "shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    setp(m, "two_sided", True)
    setp(m, "used_with_instanced_static_meshes", True)
    setp(m, "used_with_nanite", True)
    vc, lin = linear_vc(m, -900, 0)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1300, 200)
    var = custom(m, "float n = frac(sin(dot(floor(P.xy/700.0), float2(12.9898,78.233)))*43758.5453);\n"
                    "return lerp(float3(0.85,0.9,0.75), float3(1.15,1.05,0.8), n);",
                 ["P"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -1000, 200, "Variation de teinte")
    link(wp, "", var, "P")
    base = expr(m, unreal.MaterialExpressionMultiply, -600, 0)
    link(lin, "", base, "A")
    link(var, "", base, "B")
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    sss = expr(m, unreal.MaterialExpressionMultiply, -600, 150, const_b=0.6)
    link(base, "", sss, "A")
    mel.connect_material_property(sss, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    mel.connect_material_property(scalar(m, "Roughness", 0.75, -600, 300), "", unreal.MaterialProperty.MP_ROUGHNESS)
    try:
        fn = unreal.load_asset("/Engine/Functions/Engine_MaterialFunctions01/WorldPositionOffset/SimpleGrassWind")
        call = expr(m, unreal.MaterialExpressionMaterialFunctionCall, -600, 450)
        setp(call, "material_function", fn)
        link(scalar(m, "WindIntensity", 0.35, -900, 450), "", call, "WindIntensity")
        link(vc, "A", call, "WindWeight")
        link(scalar(m, "WindSpeed", 0.6, -900, 550), "", call, "WindSpeed")
        mel.connect_material_property(call, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    except Exception as e:  # noqa
        warn("vent non configure : %s" % e)
    return finish(m)


def make_rock_material():
    m = new_material("M_RockVC")
    setp(m, "used_with_instanced_static_meshes", True)
    setp(m, "used_with_nanite", True)
    vc, lin = linear_vc(m, -900, 0)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1300, 200)
    detail = custom(m, """
struct H { float h(float3 p){ return frac(sin(dot(p, float3(12.9898,78.233,37.719)))*43758.5453); }
 float n(float3 p){ float3 i=floor(p); float3 f=frac(p); f=f*f*(3-2*f);
  return lerp(lerp(lerp(h(i),h(i+float3(1,0,0)),f.x),lerp(h(i+float3(0,1,0)),h(i+float3(1,1,0)),f.x),f.y),
              lerp(lerp(h(i+float3(0,0,1)),h(i+float3(1,0,1)),f.x),lerp(h(i+float3(0,1,1)),h(i+float3(1,1,1)),f.x),f.y),f.z); } };
H q; float3 p = P/40.0;
float v = q.n(p)*0.5 + q.n(p*2.3)*0.3 + q.n(p*6.1)*0.2;
return 0.7 + 0.55*v;""", ["P"], unreal.CustomMaterialOutputType.CMOT_FLOAT1, -1000, 200, "Grain de la roche")
    link(wp, "", detail, "P")
    base = expr(m, unreal.MaterialExpressionMultiply, -600, 0)
    link(lin, "", base, "A")
    link(detail, "", base, "B")
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(m, "Roughness", 0.85, -600, 300), "", unreal.MaterialProperty.MP_ROUGHNESS)
    return finish(m)


def make_glow_material():
    m = new_material("M_AetherGlow")
    setp(m, "shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    setp(m, "blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    setp(m, "two_sided", True)
    col = vector(m, "Color", (4, 4, 4, 1), -900, 0)
    op = scalar(m, "Opacity", 1.0, -900, 200)
    fres = expr(m, unreal.MaterialExpressionFresnel, -900, 350)
    soft = expr(m, unreal.MaterialExpressionOneMinus, -700, 350)
    link(fres, "", soft, "")
    a = expr(m, unreal.MaterialExpressionMultiply, -600, 0)
    link(col, "", a, "A")
    link(op, "", a, "B")
    b = expr(m, unreal.MaterialExpressionMultiply, -400, 100)
    link(a, "", b, "A")
    link(soft, "", b, "B")
    mel.connect_material_property(b, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    return finish(m)


WATER_NORMAL_HLSL = """
struct W { float2 g(float2 p, float2 d, float k, float a, float t){ return d*k*a*cos(dot(d,p)*k + t); } };
W w; float2 p = P.xy/100.0; float t = T;
float2 s = 0;
s += w.g(p, normalize(float2( 1.0, 0.3)), 0.35, 0.10, t*1.3);
s += w.g(p, normalize(float2(-0.4, 1.0)), 0.62, 0.06, t*1.9);
s += w.g(p, normalize(float2( 0.8,-0.7)), 1.30, 0.03, t*2.7);
s += w.g(p, normalize(float2(-0.9,-0.2)), 2.70, 0.015, t*3.9);
s += w.g(p, normalize(float2( 0.2, 0.9)), 5.10, 0.008, t*5.3);
s += w.g(p, normalize(float2(-0.6, 0.6)), 9.70, 0.004, t*7.1);
return normalize(float3(-s.x*Strength, -s.y*Strength, 1.0));
"""


def make_water_material():
    m = new_material("M_Water")
    setp(m, "shading_model", unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
    setp(m, "blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    setp(m, "two_sided", True)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1200, 0)
    tm = expr(m, unreal.MaterialExpressionTime, -1200, 150)
    strength = scalar(m, "WaveStrength", 1.0, -1200, 250)
    n = custom(m, WATER_NORMAL_HLSL, ["P", "T", "Strength"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -800, 0, "Vagues procedurales")
    link(wp, "", n, "P")
    link(tm, "", n, "T")
    link(strength, "", n, "Strength")
    mel.connect_material_property(n, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(vector(m, "BaseColor", (0.02, 0.06, 0.07, 1), -500, 200), "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(m, "Roughness", 0.03, -500, 300), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(m, "Specular", 1.0, -500, 380), "", unreal.MaterialProperty.MP_SPECULAR)
    try:
        out = expr(m, unreal.MaterialExpressionSingleLayerWaterMaterialOutput, -200, 500)
        scat = vector(m, "Scattering", (0.03, 0.09, 0.1, 1), -500, 500)
        absorb = vector(m, "Absorption", (0.38, 0.09, 0.06, 1), -500, 620)
        for pin_names, src in ((("ScatteringCoefficients", "Scattering Coefficients"), scat),
                               (("AbsorptionCoefficients", "Absorption Coefficients"), absorb)):
            ok = False
            for pin in pin_names:
                if mel.connect_material_expressions(src, "", out, pin):
                    ok = True
                    break
            if not ok:
                warn("eau : entree %s introuvable" % pin_names[0])
    except Exception as e:  # noqa
        warn("sortie Single Layer Water non configuree : %s" % e)
    return finish(m)


LANDSCAPE_COLOR_HLSL = """
struct N { float h(float2 p){ return frac(sin(dot(p, float2(127.1,311.7)))*43758.5453); }
 float n(float2 p){ float2 i=floor(p); float2 f=frac(p); float2 u=f*f*(3-2*f);
  return lerp(lerp(h(i),h(i+float2(1,0)),u.x), lerp(h(i+float2(0,1)),h(i+float2(1,1)),u.x), u.y); }
 float fbm(float2 p){ float v=0, a=0.5; for(int k=0;k<5;k++){ v+=a*n(p); p=p*2.03+17.0; a*=0.5; } return v; } };
N q;
float2 p = P.xy/100.0;
float hm = (P.z - Sea)/100.0;
float slope = 1.0 - saturate(Nrm.z);
float macro = q.fbm(p/70.0);
float mid   = q.fbm(p/9.0);
float micro = q.fbm(p*1.7);
float3 grassA = float3(0.085,0.15,0.035), grassB = float3(0.20,0.25,0.07), dry = float3(0.30,0.27,0.12);
float3 c = lerp(grassA, grassB, macro);
c = lerp(c, dry, saturate(q.fbm(p/30.0)*1.8-0.85));
c *= 0.82 + 0.36*micro;
float3 rock = lerp(float3(0.20,0.19,0.18), float3(0.36,0.34,0.31), mid) * (0.85+0.3*micro);
float3 sand = float3(0.58,0.52,0.39) * (0.9+0.2*micro);
float3 snow = float3(0.86,0.9,0.95) * (0.95+0.05*micro);
float3 ash  = float3(0.11,0.10,0.095) * (0.75+0.5*mid);
float alpine = smoothstep(260.0, 480.0, hm + (macro-0.5)*90.0);
c = lerp(c, lerp(c*0.8, rock, 0.55), alpine);
float vd = distance(P.xy, Volc.xy)/100.0;
float volc = (1.0 - smoothstep(850.0, 1400.0, vd + (macro-0.5)*260.0)) * step(30.0, hm);
c = lerp(c, ash, volc);
float sandT = 1.0 - smoothstep(1.2, 4.5, hm + (mid-0.5)*2.5);
c = lerp(c, sand, sandT);
float rockT = smoothstep(0.24, 0.42, slope + (mid-0.5)*0.18);
c = lerp(c, rock, rockT);
float snowT = smoothstep(560.0, 650.0, hm + (macro-0.5)*90.0) * (1.0 - smoothstep(0.45, 0.62, slope));
c = lerp(c, snow, snowT);
float under = 1.0 - smoothstep(-0.8, 0.4, hm);
c = lerp(c, sand*0.55, under);
return c;
"""

LANDSCAPE_ROUGH_HLSL = """
float hm = (P.z - Sea)/100.0;
float slope = 1.0 - saturate(Nrm.z);
float r = 0.92;
r = lerp(r, 0.78, smoothstep(0.24, 0.42, slope));
r = lerp(r, 0.55, smoothstep(560.0, 650.0, hm));
r = lerp(r, 0.35, 1.0 - smoothstep(-0.5, 1.2, hm));    // sable mouille
return r;
"""

LANDSCAPE_NORMAL_HLSL = """
struct N { float h(float2 p){ return frac(sin(dot(p, float2(127.1,311.7)))*43758.5453); }
 float n(float2 p){ float2 i=floor(p); float2 f=frac(p); float2 u=f*f*(3-2*f);
  return lerp(lerp(h(i),h(i+float2(1,0)),u.x), lerp(h(i+float2(0,1)),h(i+float2(1,1)),u.x), u.y); }
 float f(float2 p){ return n(p)*0.55 + n(p*2.1)*0.3 + n(p*4.7)*0.15; } };
N q;
float2 p = P.xy/60.0;
float e = 0.05;
float c0 = q.f(p);
float dx = q.f(p+float2(e,0)) - c0;
float dy = q.f(p+float2(0,e)) - c0;
float slope = 1.0 - saturate(Nrm.z);
float k = Strength * (0.6 + 1.6*smoothstep(0.2, 0.45, slope));
return normalize(float3(-dx/e*k, -dy/e*k, 1.0));
"""


def make_landscape_material(cfg):
    m = new_material("M_Landscape")
    setp(m, "used_with_nanite", True)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1400, 0)
    nrm = expr(m, unreal.MaterialExpressionVertexNormalWS, -1400, 150)
    sea = scalar(m, "SeaLevel", float(cfg.get("seaLevelZ", 0.0)), -1400, 250)
    vx, vy = cfg.get("volcano", [0, 0])
    volc = vector(m, "VolcanoXY", (float(vx), float(vy), 0, 0), -1400, 350)
    col = custom(m, LANDSCAPE_COLOR_HLSL, ["P", "Nrm", "Sea", "Volc"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -900, 0, "Couleur du terrain")
    rough = custom(m, LANDSCAPE_ROUGH_HLSL, ["P", "Nrm", "Sea"], unreal.CustomMaterialOutputType.CMOT_FLOAT1, -900, 300, "Rugosite")
    strength = scalar(m, "DetailNormalStrength", 0.35, -1400, 500)
    nd = custom(m, LANDSCAPE_NORMAL_HLSL, ["P", "Nrm", "Strength"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -900, 500, "Relief de detail")
    for c in (col, rough):
        link(wp, "", c, "P")
        link(nrm, "", c, "Nrm")
        link(sea, "", c, "Sea")
    link(volc, "", col, "Volc")
    link(wp, "", nd, "P")
    link(nrm, "", nd, "Nrm")
    link(strength, "", nd, "Strength")
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(nd, "", unreal.MaterialProperty.MP_NORMAL)
    return finish(m)


# ---------------------------------------------------------------------------
# Import FBX
# ---------------------------------------------------------------------------

def import_fbx(src, dest, skeletal):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", src)
    task.set_editor_property("destination_path", dest)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    ui = unreal.FbxImportUI()
    setp(ui, "import_mesh", True)
    setp(ui, "import_textures", False)
    setp(ui, "import_materials", False)
    setp(ui, "import_as_skeletal", skeletal)
    setp(ui, "import_animations", skeletal)
    setp(ui, "create_physics_asset", skeletal)
    setp(ui, "mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH if skeletal else unreal.FBXImportType.FBXIT_STATIC_MESH)
    if skeletal:
        d = ui.get_editor_property("skeletal_mesh_import_data")
        setp(d, "vertex_color_import_option", unreal.VertexColorImportOption.REPLACE)
        setp(d, "import_morph_targets", False)
        a = ui.get_editor_property("anim_sequence_import_data")
        setp(a, "animation_length", unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    else:
        d = ui.get_editor_property("static_mesh_import_data")
        setp(d, "vertex_color_import_option", unreal.VertexColorImportOption.REPLACE)
        setp(d, "combine_meshes", True)
        setp(d, "auto_generate_collision", True)
        setp(d, "generate_lightmap_u_vs", False)
        setp(d, "build_nanite", True)
    task.set_editor_property("options", ui)
    asset_tools.import_asset_tasks([task])
    return list(task.get_editor_property("imported_object_paths") or [])


def assign_skeletal_material(path, mat):
    sk = unreal.load_asset(path)
    if not sk:
        warn("mesh introuvable : " + path)
        return
    mats = sk.get_editor_property("materials")
    for sm in mats:
        sm.set_editor_property("material_interface", mat)
    sk.set_editor_property("materials", mats)
    eal.save_loaded_asset(sk)


def assign_static_material(path, mat):
    sm = unreal.load_asset(path)
    if not sm:
        warn("mesh introuvable : " + path)
        return
    try:
        for i in range(max(1, len(sm.get_editor_property("static_materials")))):
            sm.set_material(i, mat)
    except Exception:  # noqa
        sm.set_material(0, mat)
    eal.save_loaded_asset(sm)


def import_all(mats):
    try:
        # importeur FBX "classique" : options d'import previsibles (UE 5.3 - 5.6)
        unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX false")
    except Exception:  # noqa
        pass
    count = 0
    for group, dest_root in (("Creatures", GAME + "/Creatures"), ("Characters", GAME + "/Characters")):
        base = os.path.join(ART, group)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            fbx = os.path.join(base, name, "SK_%s.fbx" % name)
            if not os.path.isfile(fbx):
                continue
            dest = "%s/%s" % (dest_root, name)
            import_fbx(fbx, dest, True)
            assign_skeletal_material("%s/SK_%s" % (dest, name), mats["creature"])
            anims = [a for a in eal.list_assets(dest, recursive=False) if "_Anim_" in a]
            log("%-13s importe (%d animations)" % (name, len(anims)))
            count += 1
    env = os.path.join(ART, "Environment")
    for f in sorted(os.listdir(env)) if os.path.isdir(env) else []:
        if not f.endswith(".fbx"):
            continue
        name = f[:-4]
        import_fbx(os.path.join(env, f), GAME + "/Environment", False)
        if any(k in name for k in ("Tree", "Bush", "Grass")):
            mat = mats["foliage"]
        elif "Shrine" in name:
            mat = mats["creature"]
        else:
            mat = mats["rock"]
        assign_static_material("%s/Environment/%s" % (GAME, name), mat)
        count += 1
    log("%d assets importes" % count)


# ---------------------------------------------------------------------------
# Niveau
# ---------------------------------------------------------------------------

def actors_of(cls):
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return [a for a in eas.get_all_level_actors() if isinstance(a, cls)]


def spawn(cls, loc=(0, 0, 0), rot=(0, 0, 0), label=None):
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    a = eas.spawn_actor_from_class(cls, unreal.Vector(*loc), unreal.Rotator(*rot))
    if label:
        a.set_actor_label(label)
    return a


def get_or_spawn(cls, label, loc=(0, 0, 0), rot=(0, 0, 0), tag=None):
    for a in actors_of(cls):
        if tag is None or unreal.Name(tag) in a.tags:
            return a
    a = spawn(cls, loc, rot, label)
    if tag:
        a.tags = [unreal.Name(tag)]
    return a


def setup_level(mats, cfg):
    # --- Soleil
    dls = actors_of(unreal.DirectionalLight)
    sun = next((d for d in dls if unreal.Name("Sun") in d.tags), dls[0] if dls else None)
    if sun is None:
        sun = spawn(unreal.DirectionalLight, (0, 0, 50000), (0, -40, -35), "Aether_Soleil")
    sun.tags = [unreal.Name("Sun")]
    sun.root_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    lc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    for k, v in (("intensity", 10.0), ("atmosphere_sun_light", True), ("atmosphere_sun_light_index", 0),
                 ("cast_cloud_shadows", True), ("light_source_angle", 0.5357), ("enable_light_shaft_bloom", True),
                 ("dynamic_shadow_cascades", 4), ("light_color", unreal.Color(255, 244, 230, 255))):
        setp(lc, k, v)
    # --- Lune
    moon = next((d for d in actors_of(unreal.DirectionalLight) if unreal.Name("Moon") in d.tags), None)
    if moon is None:
        moon = spawn(unreal.DirectionalLight, (0, 0, 50000), (0, 40, 145), "Aether_Lune")
        moon.tags = [unreal.Name("Moon")]
    moon.root_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    mc = moon.get_component_by_class(unreal.DirectionalLightComponent)
    for k, v in (("intensity", 0.4), ("atmosphere_sun_light", True), ("atmosphere_sun_light_index", 1),
                 ("light_color", unreal.Color(140, 165, 255, 255)), ("cast_cloud_shadows", True)):
        setp(mc, k, v)
    # --- Ciel, nuages, brouillard, sky light
    get_or_spawn(unreal.SkyAtmosphere, "Aether_Atmosphere")
    get_or_spawn(unreal.VolumetricCloud, "Aether_Nuages")
    sky = get_or_spawn(unreal.SkyLight, "Aether_SkyLight")
    sky.root_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    setp(sky.get_component_by_class(unreal.SkyLightComponent), "real_time_capture", True)
    fog = get_or_spawn(unreal.ExponentialHeightFog, "Aether_Brouillard")
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    for k, v in (("fog_density", 0.015), ("fog_height_falloff", 0.035), ("volumetric_fog", True),
                 ("volumetric_fog_scattering_distribution", 0.45), ("volumetric_fog_extinction_scale", 1.2)):
        setp(fc, k, v)
    # --- Post-process global
    pp = get_or_spawn(unreal.PostProcessVolume, "Aether_PostProcess")
    setp(pp, "unbound", True)
    s = pp.get_editor_property("settings")
    for k, v in (("override_bloom_intensity", True), ("bloom_intensity", 0.6),
                 ("override_vignette_intensity", True), ("vignette_intensity", 0.28),
                 ("override_lumen_scene_lighting_quality", True), ("lumen_scene_lighting_quality", 2.0),
                 ("override_lumen_scene_detail", True), ("lumen_scene_detail", 2.0),
                 ("override_lumen_final_gather_quality", True), ("lumen_final_gather_quality", 2.0),
                 ("override_lumen_reflection_quality", True), ("lumen_reflection_quality", 2.0),
                 ("override_lumen_max_trace_distance", True), ("lumen_max_trace_distance", 40000.0),
                 ("override_auto_exposure_bias", True), ("auto_exposure_bias", 0.3),
                 ("override_film_grain_intensity", True), ("film_grain_intensity", 0.08),
                 ("override_ambient_occlusion_intensity", True), ("ambient_occlusion_intensity", 0.6),
                 ("override_color_saturation", True), ("color_saturation", unreal.Vector4(1.06, 1.06, 1.06, 1.0))):
        setp(s, k, v)
    setp(pp, "settings", s)

    # --- Landscape
    lands = actors_of(unreal.LandscapeProxy)
    if not lands:
        warn("AUCUN LANDSCAPE dans le niveau : importe d'abord la heightmap (voir README, etape 3).")
    for l in lands:
        setp(l, "landscape_material", mats["landscape"])
        log("materiau applique au landscape " + l.get_actor_label())

    # --- Ocean / lacs (surface d'eau unique au niveau de la mer)
    sea = float(cfg.get("seaLevelZ", 0.0))
    size_m = float(cfg["landscape"]["sizeKm"]) * 1000.0
    water = next((a for a in actors_of(unreal.StaticMeshActor) if unreal.Name("AetherWater") in a.tags), None)
    if water is None:
        water = spawn(unreal.StaticMeshActor, (0, 0, sea), (0, 0, 0), "Aether_Ocean")
        water.tags = [unreal.Name("AetherWater")]
    smc = water.static_mesh_component
    smc.set_mobility(unreal.ComponentMobility.MOVABLE)
    smc.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/Plane"))
    smc.set_material(0, mats["water"])
    smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    setp(smc, "cast_shadow", False)
    water.set_actor_location(unreal.Vector(0, 0, sea), False, False)
    water.set_actor_scale3d(unreal.Vector(size_m * 1.75, size_m * 1.75, 1))   # plan de 1 m -> couvre la carte + horizon

    # --- Mode de jeu
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        gm = unreal.load_class(None, "/Script/Aetherwild.AetherGameMode")
        setp(world.get_world_settings(), "default_game_mode", gm)
    except Exception as e:  # noqa
        warn("game mode non defini sur le niveau (%s) - il l'est deja dans DefaultEngine.ini" % e)

    # --- Sauvegarde
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        unreal.EditorLoadingAndSavingUtils.save_map(world, GAME + "/Maps/L_Aetherwild")
        log("niveau sauvegarde : %s/Maps/L_Aetherwild" % GAME)
    except Exception as e:  # noqa
        warn("sauvegarde du niveau a faire a la main (Fichier > Enregistrer sous > %s/Maps/L_Aetherwild) : %s" % (GAME, e))


def run(import_assets=True, level=True):
    cfg = world_config()
    for d in (MAT_DIR, GAME + "/Maps", GAME + "/Creatures", GAME + "/Environment", GAME + "/Characters"):
        if not eal.does_directory_exist(d):
            eal.make_directory(d)
    mats = {
        "creature": make_creature_material(),
        "foliage": make_foliage_material(),
        "rock": make_rock_material(),
        "glow": make_glow_material(),
        "water": make_water_material(),
        "landscape": make_landscape_material(cfg),
    }
    if import_assets:
        import_all(mats)
    if level:
        setup_level(mats, cfg)
    log("Installation terminee. Appuie sur Play (Alt+P) !")


if __name__ == "__main__":
    run()
