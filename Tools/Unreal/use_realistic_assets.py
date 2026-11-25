"""
AETHERWILD - Branche automatiquement des assets photorealistes (Megascans / Fab) dans le jeu.
===========================================================================================
1. Ajoute des packs au projet (Fab dans l'editeur : Window > Fab, ou Bridge/Megascans) :
     - surfaces : herbe/sol, roche, neige, sable, sol volcanique (textures BaseColor + Normal + ORM)
     - plantes 3D : arbres (feuillus, coniferes), buissons, herbes/fleurs  (de preference en Nanite)
     - rochers / falaises 3D
2. Lance ce script : Outils > Executer un script Python > Tools/Unreal/use_realistic_assets.py

Le script :
  * cherche les assets par mots-cles (anglais, noms Megascans/Fab) en dehors de /Game/Aetherwild ;
  * cree M_LandscapeRealistic (textures reelles melangees par altitude/pente, comme M_Landscape)
    et l'applique au Landscape ;
  * reecrit Content/Data/scatter.json avec les vrais arbres/herbes/rochers (sauvegarde de l'ancien) ;
  * affiche ce qu'il a trouve et ce qui manque.
Tu peux le relancer a chaque nouvel ajout de pack.
"""
import json
import os
import shutil
import sys

import unreal

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
except NameError:   # execute depuis la console : on suppose le dossier du projet
    sys.path.insert(0, os.path.join(unreal.Paths.project_dir(), "Tools", "Unreal"))
import setup_aetherwild as base  # noqa: E402

ROOT = base.ROOT
eal = unreal.EditorAssetLibrary
ar = unreal.AssetRegistryHelpers.get_asset_registry()

SURFACES = {
    # cle : (mots-cles, couleur de secours lineaire, taille de la texture au sol en metres)
    "Grass": (["grass", "meadow", "lawn", "forest_floor", "forestfloor", "moss", "ground"], (0.12, 0.19, 0.05), 3.0),
    "Rock":  (["rock", "cliff", "granite", "basalt", "stone", "slate"], (0.28, 0.26, 0.24), 6.0),
    "Snow":  (["snow", "ice", "frost"], (0.86, 0.9, 0.95), 4.0),
    "Sand":  (["sand", "beach", "gravel", "pebbles"], (0.58, 0.52, 0.39), 3.0),
    "Ash":   (["volcanic", "lava", "ash", "scoria", "soil", "dirt", "mud"], (0.11, 0.10, 0.095), 4.0),
}
MESHES = {
    "pine":      ["pine", "spruce", "fir", "conifer", "larch", "cedar"],
    "broadleaf": ["oak", "beech", "birch", "maple", "alder", "linden", "elm", "broadleaf", "deciduous", "tree"],
    "bush":      ["bush", "shrub", "fern", "hedge", "juniper"],
    "grass":     ["grass", "clover", "flower", "weed", "dandelion", "heather", "plant"],
    "cliff":     ["cliff", "rockface", "formation", "rock_wall", "massive"],
    "rock":      ["rock", "stone", "boulder", "pebble"],
}


def log(m):
    unreal.log("[Aetherwild/realiste] " + m)


def all_assets(class_name):
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", class_name)],
                          package_paths=["/Game"], recursive_paths=True)
    out = []
    for a in ar.get_assets(flt):
        p = str(a.package_name)
        if p.startswith("/Game/Aetherwild"):
            continue
        out.append((p, str(a.asset_name)))
    return out


def object_path(pkg, name):
    return "%s.%s" % (pkg, name)


# ---------------------------------------------------------------------------
# Surfaces -> materiau de terrain
# ---------------------------------------------------------------------------

def classify_texture(name):
    n = name.lower()
    if any(k in n for k in ("normal", "_n", "nrm")) and not n.endswith("_nd"):
        if n.endswith("_n") or "normal" in n or "nrm" in n:
            return "N"
    if any(k in n for k in ("orm", "ard", "arm", "orde", "ordp", "_ord")):
        return "ORM"
    if n.endswith("_r") or "roughness" in n:
        return "R"
    if any(k in n for k in ("basecolor", "albedo", "diffuse", "_d", "_color", "_bc")):
        if n.endswith("_d") or "basecolor" in n or "albedo" in n or "diffuse" in n or n.endswith("_bc") or n.endswith("_color"):
            return "D"
    return None


def find_surfaces():
    textures = all_assets("Texture2D")
    by_folder = {}
    for pkg, name in textures:
        folder = pkg.rsplit("/", 1)[0]
        kind = classify_texture(name)
        if kind:
            by_folder.setdefault(folder, {})[kind] = object_path(pkg, name)
    found = {}
    for key, (words, _, _) in SURFACES.items():
        best = None
        for folder, kinds in by_folder.items():
            low = folder.lower()
            if "D" not in kinds:
                continue
            if any(w in low for w in words):
                score = len(kinds) + (2 if "N" in kinds else 0)
                if key == "Grass" and any(w in low for w in ("rock", "cliff", "snow", "sand")):
                    continue
                if best is None or score > best[0]:
                    best = (score, folder, kinds)
        if best:
            found[key] = best[2]
            log("surface %-5s -> %s  (%s)" % (key, best[1], ", ".join(sorted(best[2]))))
        else:
            log("surface %-5s -> AUCUNE (couleur procedurale conservee)" % key)
    return found


WEIGHTS_HLSL = """
struct N { float h(float2 p){ return frac(sin(dot(p, float2(127.1,311.7)))*43758.5453); }
 float n(float2 p){ float2 i=floor(p); float2 f=frac(p); float2 u=f*f*(3-2*f);
  return lerp(lerp(h(i),h(i+float2(1,0)),u.x), lerp(h(i+float2(0,1)),h(i+float2(1,1)),u.x), u.y); }
 float fbm(float2 p){ float v=0, a=0.5; for(int k=0;k<4;k++){ v+=a*n(p); p=p*2.03+17.0; a*=0.5; } return v; } };
N q;
float2 p = P.xy/100.0;
float hm = (P.z - Sea)/100.0;
float slope = 1.0 - saturate(Nrm.z);
float macro = q.fbm(p/70.0);
float mid = q.fbm(p/9.0);
float wRock = saturate(smoothstep(0.24, 0.42, slope + (mid-0.5)*0.18) + 0.55*smoothstep(260.0, 480.0, hm + (macro-0.5)*90.0));
float wSnow = smoothstep(560.0, 650.0, hm + (macro-0.5)*90.0) * (1.0 - smoothstep(0.45, 0.62, slope));
float wSand = max(1.0 - smoothstep(1.2, 4.5, hm + (mid-0.5)*2.5), 1.0 - smoothstep(-0.8, 0.4, hm));
float vd = distance(P.xy, Volc.xy)/100.0;
float wAsh = (1.0 - smoothstep(850.0, 1400.0, vd + (macro-0.5)*260.0)) * step(30.0, hm);
return float4(wRock, wSnow, wSand, wAsh);
"""

MACRO_HLSL = """
float2 p = P.xy/100.0;
float a = frac(sin(dot(floor(p/37.0), float2(12.9898,78.233)))*43758.5453);
float b = frac(sin(dot(floor(p/11.0), float2(39.346,11.135)))*24634.6345);
return lerp(0.82, 1.15, lerp(a, b, 0.35));
"""


def mask(m, src, channel, x, y):
    cm = base.expr(m, unreal.MaterialExpressionComponentMask, x, y, r=channel == "r", g=channel == "g", b=channel == "b", a=channel == "a")
    base.link(src, "", cm, "")
    return cm


def surface_nodes(m, key, tex, uv, x, y):
    """Renvoie (couleur, normale, rugosite, ao) pour une surface (textures reelles ou constantes)."""
    words, fallback, _ = SURFACES[key]
    shared = unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS
    if not tex:
        c = base.expr(m, unreal.MaterialExpressionConstant3Vector, x, y, constant=unreal.LinearColor(*fallback, 1.0))
        n = base.expr(m, unreal.MaterialExpressionConstant3Vector, x, y + 80, constant=unreal.LinearColor(0, 0, 1, 1))
        r = base.expr(m, unreal.MaterialExpressionConstant, x, y + 160, r=0.85)
        ao = base.expr(m, unreal.MaterialExpressionConstant, x, y + 220, r=1.0)
        return c, n, r, ao
    d = base.expr(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=key + "_Color",
                  texture=unreal.load_asset(tex["D"]), sampler_source=shared)
    base.link(uv[key], "", d, "UVs")
    if "N" in tex:
        n = base.expr(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y + 260, parameter_name=key + "_Normal",
                      texture=unreal.load_asset(tex["N"]), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, sampler_source=shared)
        base.link(uv[key], "", n, "UVs")
    else:
        n = base.expr(m, unreal.MaterialExpressionConstant3Vector, x, y + 260, constant=unreal.LinearColor(0, 0, 1, 1))
    if "ORM" in tex:
        orm = base.expr(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y + 520, parameter_name=key + "_ORM",
                        texture=unreal.load_asset(tex["ORM"]), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS, sampler_source=shared)
        base.link(uv[key], "", orm, "UVs")
        r = mask(m, orm, "g", x + 250, y + 520)
        ao = mask(m, orm, "r", x + 250, y + 600)
    elif "R" in tex:
        rt = base.expr(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y + 520, parameter_name=key + "_Roughness",
                       texture=unreal.load_asset(tex["R"]), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE, sampler_source=shared)
        base.link(uv[key], "", rt, "UVs")
        r = rt
        ao = base.expr(m, unreal.MaterialExpressionConstant, x + 250, y + 600, r=1.0)
    else:
        r = base.expr(m, unreal.MaterialExpressionConstant, x, y + 520, r=0.85)
        ao = base.expr(m, unreal.MaterialExpressionConstant, x + 250, y + 600, r=1.0)
    return d, n, r, ao


def lerp_chain(m, layers, weights, idx, x, y):
    """layers[key] = noeud ; ordre de melange : Grass -> Ash -> Sand -> Rock -> Snow."""
    cur = layers["Grass"][idx]
    order = [("Ash", "a"), ("Sand", "b"), ("Rock", "r"), ("Snow", "g")]
    for i, (key, ch) in enumerate(order):
        l = base.expr(m, unreal.MaterialExpressionLinearInterpolate, x + i * 220, y)
        base.link(cur, "", l, "A")
        base.link(layers[key][idx], "", l, "B")
        base.link(weights[ch], "", l, "Alpha")
        cur = l
    return cur


def make_realistic_landscape_material(found, cfg):
    m = base.new_material("M_LandscapeRealistic")
    base.setp(m, "used_with_nanite", True)
    wp = base.expr(m, unreal.MaterialExpressionWorldPosition, -3000, 0)
    nrm = base.expr(m, unreal.MaterialExpressionVertexNormalWS, -3000, 150)
    sea = base.scalar(m, "SeaLevel", float(cfg.get("seaLevelZ", 0.0)), -3000, 250)
    vx, vy = cfg.get("volcano", [0, 0])
    volc = base.vector(m, "VolcanoXY", (float(vx), float(vy), 0, 0), -3000, 350)
    w = base.custom(m, WEIGHTS_HLSL, ["P", "Nrm", "Sea", "Volc"], unreal.CustomMaterialOutputType.CMOT_FLOAT4, -2600, 0, "Poids des couches")
    for nm, src in (("P", wp), ("Nrm", nrm), ("Sea", sea), ("Volc", volc)):
        base.link(src, "", w, nm)
    weights = {ch: mask(m, w, ch, -2300, i * 90) for i, ch in enumerate("rgba")}

    # UV monde : une echelle par surface (taille physique de la texture)
    xy = base.expr(m, unreal.MaterialExpressionComponentMask, -2600, 600, r=True, g=True)
    base.link(wp, "", xy, "")
    uv = {}
    for i, (key, (_, _, size_m)) in enumerate(SURFACES.items()):
        tile = base.scalar(m, key + "_TileMeters", size_m, -2600, 700 + i * 120)
        cm = base.expr(m, unreal.MaterialExpressionMultiply, -2400, 700 + i * 120, const_b=100.0)
        base.link(tile, "", cm, "A")
        div = base.expr(m, unreal.MaterialExpressionDivide, -2200, 700 + i * 120)
        base.link(xy, "", div, "A")
        base.link(cm, "", div, "B")
        uv[key] = div

    layers = {}
    for i, key in enumerate(SURFACES):
        layers[key] = surface_nodes(m, key, found.get(key), uv, -1900, i * 900)

    color = lerp_chain(m, layers, weights, 0, -1300, 0)
    normal = lerp_chain(m, layers, weights, 1, -1300, 400)
    rough = lerp_chain(m, layers, weights, 2, -1300, 800)
    ao = lerp_chain(m, layers, weights, 3, -1300, 1200)

    # variation de teinte a grande echelle : casse la repetition des textures
    macro = base.custom(m, MACRO_HLSL, ["P"], unreal.CustomMaterialOutputType.CMOT_FLOAT1, -700, -200, "Anti-repetition")
    base.link(wp, "", macro, "P")
    col = base.expr(m, unreal.MaterialExpressionMultiply, -300, 0)
    base.link(color, "", col, "A")
    base.link(macro, "", col, "B")

    mel = unreal.MaterialEditingLibrary
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(ao, "", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    return base.finish(m)


# ---------------------------------------------------------------------------
# Meshes -> scatter.json
# ---------------------------------------------------------------------------

def mesh_size_m(path):
    sm = unreal.load_asset(path)
    try:
        b = sm.get_bounding_box()
        e = b.max - b.min
        return max(e.x, e.y, e.z) / 100.0
    except Exception:  # noqa
        return 1.0


def find_meshes():
    found = {k: [] for k in MESHES}
    for pkg, name in all_assets("StaticMesh"):
        low = (pkg + "/" + name).lower()
        if any(k in low for k in ("lod", "billboard", "impostor", "_collision")) and "nanite" not in low:
            continue
        for cat in ("pine", "broadleaf", "bush", "grass", "cliff", "rock"):
            if any(w in low for w in MESHES[cat]):
                if cat == "broadleaf" and any(w in low for w in MESHES["pine"]):
                    continue
                found[cat].append(object_path(pkg, name))
                break
    # tri rochers : gros blocs -> categorie "cliff"
    big = [p for p in found["rock"] if mesh_size_m(p) > 6.0]
    found["cliff"] += big
    found["rock"] = [p for p in found["rock"] if p not in big]
    for k, v in found.items():
        log("meshes %-9s : %d" % (k, len(v)))
    return found


def rewrite_scatter(found):
    path = os.path.join(ROOT, "Content", "Data", "scatter.json")
    backup = os.path.join(ROOT, "Content", "Data", "scatter.stylise.json")
    if not os.path.exists(backup):
        shutil.copyfile(path, backup)
    with open(path) as f:
        cfg = json.load(f)
    mapping = {
        "Forets de feuillus": "broadleaf", "Forets de coniferes": "pine", "Arbres isoles": "broadleaf",
        "Buissons": "bush", "Rochers": "rock", "Blocs et falaises": "cliff", "Scories du volcan": "rock", "Herbe": "grass",
    }
    changed = 0
    for layer in cfg["layers"]:
        cat = mapping.get(layer["name"])
        if cat and found.get(cat):
            layer["meshes"] = found[cat][:8]
            if cat in ("broadleaf", "pine", "rock", "cliff"):
                layer["scale"] = [0.85, 1.15]          # les scans sont deja a l'echelle reelle
            if cat == "grass":
                layer["density"] = 9000                # touffes Megascans plus petites -> plus denses
            changed += 1
    with open(path, "w") as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)
    log("scatter.json : %d couches basculees sur des assets realistes (ancien fichier : scatter.stylise.json)" % changed)


def run():
    cfg = base.world_config()
    surfaces = find_surfaces()
    mat = make_realistic_landscape_material(surfaces, cfg)
    for l in base.actors_of(unreal.LandscapeProxy):
        base.setp(l, "landscape_material", mat)
        log("M_LandscapeRealistic applique a " + l.get_actor_label())
    rewrite_scatter(find_meshes())
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        unreal.EditorLoadingAndSavingUtils.save_map(world, base.GAME + "/Maps/L_Aetherwild")
    except Exception:  # noqa
        pass
    log("Termine. Lance le jeu : la vegetation et le terrain utilisent maintenant les assets realistes.")


if __name__ == "__main__":
    run()
