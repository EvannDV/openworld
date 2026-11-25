"""
AETHERWILD - Integre automatiquement un pack de creatures Fab / Marketplace dans le jeu.
======================================================================================
Etapes :
  1. Dans l'editeur Unreal : Window > Fab > ouvre le pack > "Add to My Library" puis "Add to Project".
     (Le pack arrive dans /Game/<NomDuPack>/ ou /Game/Fab/...)
  2. Outils > Executer un script Python... > Tools/Unreal/import_fab_creatures.py
     ou, pour cibler un dossier precis, dans la console Python :
        import import_fab_creatures as f; f.run("/Game/NomDuPack")
  3. Relance le jeu : les nouvelles creatures apparaissent dans le monde, sont capturables,
     combattent, et les grandes sont chevauchables.

Pour chaque SkeletalMesh trouve, le script :
  * retrouve ses animations (meme squelette) et reconnait Idle / Walk / Run / Attack / Fly / Swim
    d'apres leurs noms ;
  * devine element, rarete, biomes, statistiques, capacites et comportement (taille, nom, animations) ;
  * ajoute (ou met a jour) une espece dans Content/Data/species.json avec un bloc "visual"
    pointant vers les vrais assets (ancienne version sauvegardee dans species.backup.json) ;
  * ecrit un rapport : Saved/Aetherwild_import_report.txt
Tout est modifiable ensuite a la main dans species.json (noms, stats, conditions de capture...).
"""
import json
import os
import re
import shutil
import sys

import unreal

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.path.join(unreal.Paths.project_dir(), "Tools", "Unreal")
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SPECIES = os.path.join(ROOT, "Content", "Data", "species.json")
ar = unreal.AssetRegistryHelpers.get_asset_registry()

# Utiliser l'Animation Blueprint fourni par le pack (si trouve) au lieu des animations directes.
# Plus fluide, mais les attaques ne s'afficheront que si l'AnimBP contient un Slot "DefaultSlot".
USE_PACK_ANIMBP = False

EXCLUDE = ("/Game/Aetherwild", "/Game/MetaHumans", "/Game/Characters/Mannequins", "/Game/StarterContent")

ANIM_KEYS = {
    "Idle":   (["idle", "breath", "stand", "wait"], ["turn", "to_", "start", "end", "hit", "death", "die", "sleep", "fly", "swim"]),
    "Walk":   (["walk"], ["start", "stop", "end", "turn", "back", "left", "right", "fly", "swim"]),
    "Run":    (["run", "gallop", "sprint", "trot", "jog"], ["start", "stop", "end", "turn", "back", "bwd", "left", "right", "_lf", "_rt", "fly", "swim", "pivot"]),
    "Attack": (["attack", "bite", "claw", "strike", "slash", "punch", "smash", "stab", "breath_fire", "firebreath", "spit", "tail_attack", "stomp", "headbutt",
                "primary", "melee", "slam", "pound", "throw", "ability"],
               ["hit_react", "hitreact", "gethit", "get_hit", "damage", "death", "die", "start", "end", "loop", "recovery", "charge_up"]),
    "Fly":    (["fly", "flying", "hover", "glide", "flap"], ["start", "land", "takeoff", "take_off", "end", "death"]),
    "Swim":   (["swim"], ["start", "end", "death"]),
}

ELEMENTS = [
    ("Fire", ["fire", "lava", "magma", "flame", "ember", "inferno", "hell", "phoenix", "salamander", "dragon"]),
    ("Frost", ["ice", "frost", "snow", "yeti", "glacier", "winter", "polar"]),
    ("Water", ["water", "sea", "ocean", "shark", "fish", "crab", "kraken", "naga", "turtle", "frog", "lizard"]),
    ("Nature", ["plant", "tree", "ent", "treant", "mushroom", "forest", "spider", "insect", "bug", "beetle", "mantis", "slime", "deer", "boar", "bear"]),
    ("Stone", ["rock", "stone", "golem", "earth", "crystal", "troll", "rhino", "armadillo"]),
    ("Storm", ["storm", "thunder", "lightning", "bird", "eagle", "griffin", "gryphon", "harpy", "wyvern", "hawk", "raven"]),
    ("Shadow", ["shadow", "ghost", "undead", "skeleton", "zombie", "demon", "bat", "wolf", "werewolf", "vampire", "dark", "spider", "scorpion"]),
    ("Light", ["light", "angel", "holy", "spirit", "unicorn", "pegasus", "sun", "star"]),
]

# capacites existantes (Content/Data/abilities.json) par element : base, niv 6, niv 12, niv 18 + coup special
LEARN = {
    "Fire":   (["morsure", "flammeche", "griffes_ardentes", "souffle_brasier", "charge_magma"], "ult_tempete_braises"),
    "Water":  (["morsure", "jet_eau", "queue_aqua", "vague", "bulle_apaisante"], "ult_maelstrom"),
    "Nature": (["morsure", "fouet_liane", "graines_explosives", "spores", "charge_sylvestre"], "ult_foret_vivante"),
    "Stone":  (["poing_roc", "jet_pierres", "carapace", "seisme", "charge"], "ult_eboulement"),
    "Storm":  (["etincelle", "morsure", "plongeon_orageux", "eclair", "cri_galvanisant"], "ult_colere_ciel"),
    "Frost":  (["morsure", "souffle_givrant", "pics_glace", "blizzard", "carapace"], "ult_zero_absolu"),
    "Shadow": (["griffe_ombre", "morsure", "bond_obscur", "voile_nocturne", "cri_galvanisant"], "ult_eclipse"),
    "Light":  (["morsure", "rayon_lumiere", "flash", "aura_soin", "charge"], "ult_supernova"),
    "Neutral": (["morsure", "charge", "cri_galvanisant", "repos", "jet_pierres"], "ult_eboulement"),
}
BIOMES = {
    "Fire": ["Volcano", "Mountains"], "Frost": ["Peaks", "Mountains"], "Water": ["Shore", "Water"],
    "Nature": ["Forest", "Plains"], "Stone": ["Mountains", "Peaks"], "Storm": ["Mountains", "Plains"],
    "Shadow": ["Forest"], "Light": ["Plains", "Forest"], "Neutral": ["Plains", "Forest", "Mountains"],
}


def log(m):
    unreal.log("[Aetherwild/Fab] " + m)


def assets(cls_pkg, cls_name, root):
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath(cls_pkg, cls_name)], package_paths=[root], recursive_paths=True)
    out = []
    for a in ar.get_assets(flt):
        p = str(a.package_name)
        if any(p.startswith(x) for x in EXCLUDE):
            continue
        out.append(a)
    return out


def obj_path(a):
    return "%s.%s" % (a.package_name, a.asset_name)


def skeleton_tag(a, tag="Skeleton"):
    try:
        v = str(a.get_tag_value(tag) or "")
    except Exception:  # noqa
        v = ""
    m = re.search(r"'?(/[^'.]+(?:\.[^']+)?)'?$", v)
    return (m.group(1) if m else v).split(".")[0]


def pick_anim(anims, key):
    words, bad = ANIM_KEYS[key]
    best, best_score = None, -1e9
    for a in anims:
        n = str(a.asset_name).lower()
        if not any(w in n for w in words) or any(b in n for b in bad):
            continue
        score = -len(n)
        if "loop" in n or "_lp" in n: score += 8
        if "in_place" in n or "inplace" in n: score += 6
        if "fwd" in n or "forward" in n: score += 5
        if key == "Attack" and ("primary" in n or "attack" in n): score += 10
        if "root" in n and "motion" in n: score -= 6
        if key == "Attack" and re.search(r"(attack|bite)_?0?1\b", n): score += 4
        if score > best_score:
            best, best_score = a, score
    return obj_path(best) if best else None


def clean_name(mesh_name):
    n = re.sub(r"^(SK|SKM|SKEL|SM)_", "", mesh_name, flags=re.I)
    n = re.sub(r"_(Mesh|LOD\d|Skeletal|Body|Main|Rig|Anim)$", "", n, flags=re.I)
    n = re.sub(r"[_\-]+", " ", n).strip()
    return " ".join(w.capitalize() for w in n.split()) or mesh_name


def guess_element(text):
    t = text.lower()
    for el, words in ELEMENTS:
        if any(w in t for w in words):
            return el
    return "Neutral"


def mesh_size_m(path):
    m = unreal.load_asset(path)
    try:
        b = m.get_bounds()
        e = b.box_extent
        return max(e.x, e.y, e.z) * 2 / 100.0
    except Exception:  # noqa
        return 2.0


def make_species(sid, name, mesh_path, anims, animbp, folder):
    size = mesh_size_m(mesh_path)
    el = guess_element(folder + " " + name)
    rarity = "Common" if size < 1.5 else "Uncommon" if size < 3 else "Rare" if size < 6 else "Epic" if size < 12 else "Legendary"
    flying = "Fly" in anims
    swimming = "Swim" in anims and "Walk" not in anims and "Run" not in anims
    movement = "Flying" if flying else ("Swimming" if swimming else ("Amphibious" if "Swim" in anims else "Ground"))
    big = size >= 2.2
    k = min(3.0, 0.6 + size * 0.35)
    lv = {"Common": (2, 10), "Uncommon": (8, 18), "Rare": (16, 28), "Epic": (26, 38), "Legendary": (40, 50)}[rarity]
    base, ult = LEARN[el]
    learn = [[1, base[0]], [1, base[1]], [lv[0] + 4, base[2]], [lv[0] + 8, base[3]], [lv[0] + 12, base[4]]]
    biomes = BIOMES[el] if movement != "Swimming" else ["Water"]
    if movement == "Flying" and "Mountains" not in biomes: biomes = biomes + ["Mountains"]
    temperament = "Aggressive" if size >= 6 else ("Territorial" if big else ("Skittish" if size < 1 else "Docile"))
    catch = {"Common": 0.55, "Uncommon": 0.35, "Rare": 0.18, "Epic": 0.08, "Legendary": 0.04}[rarity]
    visual = {"mesh": mesh_path, "anims": anims, "yaw": -90, "keepScale": True}
    if animbp and USE_PACK_ANIMBP:
        visual["animBlueprint"] = animbp
    sp = {
        "id": sid, "name": name, "element": el, "rarity": rarity,
        "description": "Creature importee du pack %s. Modifie cette description dans species.json." % folder.split("/")[-1],
        "stats": {"hp": round(40 + 14 * k), "atk": round(9 + 4 * k), "def": round(9 + 4 * k), "spi": round(9 + 3.5 * k), "spd": round(16 - 2 * k + (6 if flying else 0))},
        "catchRate": catch, "baseXP": round(35 + 30 * k),
        "biomes": biomes, "minLevel": lv[0], "maxLevel": lv[1], "size": round(size, 2), "movement": movement,
        "rideable": bool(big and ("Run" in anims or flying or swimming)),
        "walkSpeed": round(160 + 40 * k), "runSpeed": round(450 + 260 * k), "temperament": temperament,
        "color": "#888888", "accent": "#ffffff",
        "learnset": learn, "ultimate": ult,
        "assetFolder": folder, "visual": visual,
    }
    if rarity in ("Epic", "Legendary"):
        sp["capture"] = {"maxHealth": 0.35 if rarity == "Epic" else 0.25, "minTamerLevel": 8 if rarity == "Epic" else 15,
                         "hint": "Affaiblis-la fortement avant de lancer une capsule"}
    return sp


def run(root="/Game"):
    meshes = assets("/Script/Engine", "SkeletalMesh", root)
    anims_all = assets("/Script/Engine", "AnimSequence", root)
    animbps = assets("/Script/Engine", "AnimBlueprint", root)
    if not meshes:
        unreal.log_error("[Aetherwild/Fab] Aucun SkeletalMesh trouve sous %s (hors Aetherwild). Ajoute d'abord le pack au projet via Fab." % root)
        return
    meshes.sort(key=lambda a: len(str(a.asset_name)))   # le mesh de base avant ses variantes (skins)
    with open(SPECIES, encoding="utf-8") as f:
        data = json.load(f)
    backup = SPECIES.replace(".json", ".backup.json")
    if not os.path.exists(backup):
        shutil.copyfile(SPECIES, backup)
    existing = {s["id"]: s for s in data["species"]}
    report, added = [], 0
    seen_skel = {}
    for m in meshes:
        mpath = obj_path(m)
        mesh = unreal.load_asset(mpath)
        skel = mesh.get_editor_property("skeleton") if mesh else None
        skel_path = skel.get_path_name().split(".")[0] if skel else ""
        # un seul mesh par squelette (evite les doublons LOD / variantes) sauf variantes de nom differentes
        lname = str(m.asset_name).lower()
        if any(k in lname for k in ("lod", "proxy", "physics", "_hair", "groom", "_head", "_eyes", "_teeth")):
            continue
        my_anims = [a for a in anims_all if skeleton_tag(a) == skel_path]
        mapped = {}
        for key in ANIM_KEYS:
            p = pick_anim(my_anims, key)
            if p: mapped[key] = p
        if "Idle" not in mapped and my_anims:
            mapped["Idle"] = obj_path(sorted(my_anims, key=lambda a: len(str(a.asset_name)))[0])
        if "Walk" not in mapped and "Run" in mapped: mapped["Walk"] = mapped["Run"]
        if "Run" not in mapped and "Walk" in mapped: mapped["Run"] = mapped["Walk"]
        animbp = None
        for bp in animbps:
            if skeleton_tag(bp, "TargetSkeleton") == skel_path:
                animbp = "%s.%s_C" % (bp.package_name, bp.asset_name)
                break
        name = clean_name(str(m.asset_name))
        sid = re.sub(r"[^A-Za-z0-9]", "", name) or str(m.asset_name)
        if skel_path in seen_skel:
            report.append("       (apparence alternative ignoree : %s, meme squelette que %s)" % (mpath, seen_skel[skel_path]))
            continue
        seen_skel[skel_path] = sid
        folder = str(m.package_path)
        sp = make_species(sid, name, mpath, mapped, animbp, folder)
        if sid in existing:
            # on conserve les reglages faits a la main, on met juste a jour les assets
            existing[sid]["visual"] = sp["visual"]
            report.append("MAJ    %-22s %s" % (sid, mpath))
        else:
            data["species"].append(sp)
            existing[sid] = sp
            added += 1
            report.append("AJOUT  %-22s %-8s %-10s %4.1fm %-10s anims: %s%s" % (
                sid, sp["element"], sp["rarity"], sp["size"], sp["movement"], ", ".join(sorted(mapped)) or "AUCUNE",
                "  (AnimBP trouve: %s)" % animbp if animbp else ""))
        if not mapped:
            report.append("       ! aucune animation reconnue pour %s : renseigne visual.anims a la main" % sid)
    with open(SPECIES, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.makedirs(os.path.join(ROOT, "Saved"), exist_ok=True)
    with open(os.path.join(ROOT, "Saved", "Aetherwild_import_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    for line in report:
        log(line)
    log("%d nouvelle(s) creature(s) ajoutee(s) a species.json. Relance le jeu (Play) pour les voir." % added)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("/Game") else "/Game")
