"""
AETHERWILD - Applique la direction artistique "v2" a la carte du jeu.
A lancer dans l'editeur apres setup_aetherwild.py :  Outils > Executer un script Python > apply_world_v2.py
  1. importe Art/EnvironmentV2 (arbres feuillus/cerisiers/automne, sapins, arbres morts, herbes, fleurs,
     fougeres, rochers, basalte, coulees de lave) + textures de feuillage ;
  2. cree les materiaux : feuillage translucide au vent (M_LeafV2 + instances), lave craquelee incandescente ;
  3. place les coulees de lave sur le volcan ;
  4. active Content/Data/scatter_v2.json (l'ancienne vegetation est gardee dans scatter.json.v1).
"""
import os
import shutil
import sys

import unreal

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
except NameError:
    sys.path.insert(0, os.path.join(unreal.Paths.project_dir(), "Tools", "Unreal"))
import setup_aetherwild as base  # noqa: E402

ROOT = base.ROOT
SRC = os.path.join(ROOT, "Art", "EnvironmentV2")
DEST = base.GAME + "/EnvironmentV2"
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def log(m):
    unreal.log("[Aetherwild/v2] " + m)


def import_textures():
    out = {}
    folder = os.path.join(SRC, "Textures")
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".png"):
            continue
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", os.path.join(folder, f))
        t.set_editor_property("destination_path", DEST + "/Textures")
        t.set_editor_property("automated", True); t.set_editor_property("replace_existing", True); t.set_editor_property("save", True)
        tools.import_asset_tasks([t])
        out[f[:-4]] = unreal.load_asset("%s/Textures/%s" % (DEST, f[:-4]))
    return out


def make_leaf_material():
    m = base.new_material("M_LeafV2")
    base.setp(m, "shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    base.setp(m, "blend_mode", unreal.BlendMode.BLEND_MASKED)
    base.setp(m, "two_sided", True)
    base.setp(m, "used_with_instanced_static_meshes", True)
    base.setp(m, "used_with_nanite", True)
    tex = base.expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -1200, 0, parameter_name="LeafTex")
    vc = base.expr(m, unreal.MaterialExpressionVertexColor, -1200, 300)
    pir = base.expr(m, unreal.MaterialExpressionPerInstanceRandom, -1200, 450)
    var = base.custom(m, "return lerp(float3(0.85,0.9,0.8), float3(1.12,1.08,0.9), R);", ["R"],
                      unreal.CustomMaterialOutputType.CMOT_FLOAT3, -900, 450, "Variation par arbre")
    base.link(pir, "", var, "R")
    c1 = base.expr(m, unreal.MaterialExpressionMultiply, -700, 0); base.link(tex, "RGB", c1, "A"); base.link(vc, "", c1, "B")
    c2 = base.expr(m, unreal.MaterialExpressionMultiply, -500, 0); base.link(c1, "", c2, "A"); base.link(var, "", c2, "B")
    mel.connect_material_property(c2, "", unreal.MaterialProperty.MP_BASE_COLOR)
    sss = base.expr(m, unreal.MaterialExpressionMultiply, -300, 150, const_b=0.65); base.link(c2, "", sss, "A")
    mel.connect_material_property(sss, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    mel.connect_material_property(tex, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.connect_material_property(base.scalar(m, "Roughness", 0.6, -500, 300), "", unreal.MaterialProperty.MP_ROUGHNESS)
    try:
        fn = unreal.load_asset("/Engine/Functions/Engine_MaterialFunctions01/WorldPositionOffset/SimpleGrassWind")
        call = base.expr(m, unreal.MaterialExpressionMaterialFunctionCall, -500, 600)
        base.setp(call, "material_function", fn)
        base.link(base.scalar(m, "WindIntensity", 0.25, -800, 600), "", call, "WindIntensity")
        base.link(vc, "A", call, "WindWeight")
        base.link(base.scalar(m, "WindSpeed", 0.45, -800, 700), "", call, "WindSpeed")
        mel.connect_material_property(call, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    except Exception as e:  # noqa
        log("vent non configure : %s" % e)
    return base.finish(m)


LAVA_HLSL = """
float2 p = P.xy / 450.0 + float2(T * 0.004, T * 0.002);
float2 i = floor(p), f = frac(p); float md = 8, md2 = 8;
for (int y = -1; y <= 1; y++) for (int x = -1; x <= 1; x++) {
  float2 g = float2(x, y);
  float2 o = frac(sin(float2(dot(i + g, float2(127.1, 311.7)), dot(i + g, float2(269.5, 183.3)))) * 43758.5453);
  o = 0.5 + 0.45 * sin(T * 0.15 + 6.2831 * o);
  float2 r = g + o - f; float d = dot(r, r);
  if (d < md) { md2 = md; md = d; } else if (d < md2) { md2 = d; }
}
float edge = sqrt(md2) - sqrt(md);
float hot = 1.0 - smoothstep(0.0, 0.14, edge);
float pulse = 0.8 + 0.2 * sin(T * 1.3 + P.x * 0.002);
return float3(1.0, 0.32, 0.04) * hot * hot * Strength * pulse + float3(0.9, 0.1, 0.0) * 0.15 * Strength * (1.0 - hot);
"""


def make_lava_material():
    m = base.new_material("M_Lava")
    wp = base.expr(m, unreal.MaterialExpressionWorldPosition, -900, 0)
    tm = base.expr(m, unreal.MaterialExpressionTime, -900, 150)
    st = base.scalar(m, "Strength", 40.0, -900, 250)
    c = base.custom(m, LAVA_HLSL, ["P", "T", "Strength"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -600, 0, "Lave")
    base.link(wp, "", c, "P"); base.link(tm, "", c, "T"); base.link(st, "", c, "Strength")
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(base.vector(m, "Crust", (0.02, 0.015, 0.012, 1), -600, 250), "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(base.scalar(m, "Roughness", 0.7, -600, 350), "", unreal.MaterialProperty.MP_ROUGHNESS)
    return base.finish(m)


def leaf_instance(parent, name, tex):
    path = "%s/Materials/%s" % (DEST, name)
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    mi = tools.create_asset(name, DEST + "/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)
    mel.set_material_instance_texture_parameter_value(mi, "LeafTex", tex)
    eal.save_loaded_asset(mi)
    return mi


def assign_slots(sm, mapping, default):
    mats = sm.get_editor_property("static_materials")
    for i, sl in enumerate(mats):
        name = str(sl.get_editor_property("material_slot_name"))
        mat = default
        for key, m in mapping.items():
            if key.lower() in name.lower():
                mat = m
        sm.set_material(i, mat)
    eal.save_loaded_asset(sm)


def run():
    if not os.path.isdir(SRC):
        unreal.log_error("[Aetherwild/v2] Art/EnvironmentV2 introuvable : lance d'abord Tools/Blender/export_world_assets.py")
        return
    for d in (DEST, DEST + "/Textures", DEST + "/Materials"):
        if not eal.does_directory_exist(d):
            eal.make_directory(d)
    tex = import_textures()
    leaf = make_leaf_material()
    lava = make_lava_material()
    rockvc = unreal.load_asset(base.MAT_DIR + "/M_RockVC")
    grassvc = unreal.load_asset(base.MAT_DIR + "/M_FoliageVC")
    leafmats = {
        "Leaves_Green": leaf_instance(leaf, "MI_Leaves_Green", tex.get("T_Leaf_Green")),
        "Leaves_Autumn": leaf_instance(leaf, "MI_Leaves_Autumn", tex.get("T_Leaf_Autumn")),
        "Leaves_Blossom": leaf_instance(leaf, "MI_Leaves_Blossom", tex.get("T_Leaf_Blossom")),
        "Needles": leaf_instance(leaf, "MI_Needles", tex.get("T_Needles")),
        "Fern": leaf_instance(leaf, "MI_Fern", tex.get("T_Fern")),
    }
    try:
        unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX false")
    except Exception:  # noqa
        pass
    for f in sorted(os.listdir(SRC)):
        if not f.endswith(".fbx"):
            continue
        name = f[:-4]
        base.import_fbx(os.path.join(SRC, f), DEST, False)
        sm = unreal.load_asset("%s/%s" % (DEST, name))
        if not sm:
            log("import echoue : " + name); continue
        if "LavaFlows" in name:
            assign_slots(sm, {}, lava)
        elif "Grass" in name or "Flowers" in name:
            assign_slots(sm, {}, grassvc)
        elif "Fern" in name:
            assign_slots(sm, {}, leafmats["Fern"])
        elif any(k in name for k in ("Tree", "Pine", "Dead")):
            assign_slots(sm, {"Bark": rockvc, **leafmats}, rockvc)
        else:
            assign_slots(sm, {}, rockvc)
        log("importe : " + name)
    # coulees de lave (deja en coordonnees du monde)
    lava_mesh = unreal.load_asset(DEST + "/SM_V2_LavaFlows")
    if lava_mesh:
        existing = [a for a in base.actors_of(unreal.StaticMeshActor) if unreal.Name("AetherLava") in a.tags]
        act = existing[0] if existing else base.spawn(unreal.StaticMeshActor, (0, 0, 0), (0, 0, 0), "Aether_CouleesDeLave")
        act.tags = [unreal.Name("AetherLava")]
        act.static_mesh_component.set_static_mesh(lava_mesh)
        act.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
        log("coulees de lave placees sur le volcan")
    # vegetation v2
    data = os.path.join(ROOT, "Content", "Data")
    if not os.path.exists(os.path.join(data, "scatter.json.v1")):
        shutil.copyfile(os.path.join(data, "scatter.json"), os.path.join(data, "scatter.json.v1"))
    shutil.copyfile(os.path.join(data, "scatter_v2.json"), os.path.join(data, "scatter.json"))
    log("vegetation v2 activee (ancienne : scatter.json.v1)")
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        unreal.EditorLoadingAndSavingUtils.save_map(world, base.GAME + "/Maps/L_Aetherwild")
    except Exception:  # noqa
        pass
    log("Termine : appuie sur Play.")


if __name__ == "__main__":
    run()
