"""
AETHERWILD - Preparation complete du contenu, sans aucune manipulation.
Lance automatiquement par BUILD_GAME.bat (editeur ouvert avec -ExecutePythonScript), ou a la main :
    Outils > Executer un script Python > Tools/Unreal/build_all.py
Etapes : niveau -> terrain 8 km -> materiaux/assets/ciel/eau -> carte v2 -> creatures Fab -> sauvegarde -> fermeture.
"""
import json
import os
import sys
import traceback

import unreal

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.path.join(unreal.Paths.project_dir(), "Tools", "Unreal")
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MAP = "/Game/Aetherwild/Maps/L_Aetherwild"
STATUS = os.path.join(ROOT, "Saved", "build_all_status.txt")


def log(m):
    unreal.log("[Aetherwild/build] " + m)
    with open(STATUS, "a", encoding="utf-8") as f:
        f.write(m + "\n")


def step(name, fn):
    log("ETAPE : " + name)
    try:
        fn()
        log("  ok")
        return True
    except Exception:  # noqa
        log("  ECHEC :\n" + traceback.format_exc())
        return False


def open_level():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if unreal.EditorAssetLibrary.does_asset_exist(MAP):
        les.load_level(MAP)
    else:
        if not unreal.EditorAssetLibrary.does_directory_exist("/Game/Aetherwild/Maps"):
            unreal.EditorAssetLibrary.make_directory("/Game/Aetherwild/Maps")
        les.new_level(MAP)


def terrain():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if any(isinstance(a, unreal.LandscapeProxy) for a in eas.get_all_level_actors()):
        log("  terrain deja present")
        return
    w = json.load(open(os.path.join(ROOT, "Content", "Data", "world.json")))
    L = w["landscape"]
    ok = unreal.AetherEditorLibrary.import_landscape_from_heightmap(
        os.path.join(ROOT, L["heightmap"]), unreal.Vector(*L["location"]), unreal.Vector(*L["scale"]),
        L["sectionSize"], L["sectionsPerComponent"], L["components"])
    if not ok:
        raise RuntimeError("import du terrain refuse (voir le journal)")


def save():
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    unreal.EditorAssetLibrary.save_directory("/Game/Aetherwild", only_if_is_dirty=True, recursive=True)


def has_fab_creatures():
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "SkeletalMesh")], package_paths=["/Game"], recursive_paths=True)
    return any(not str(a.package_name).startswith("/Game/Aetherwild") for a in ar.get_assets(flt))


def run(quit_after=True):
    os.makedirs(os.path.dirname(STATUS), exist_ok=True)
    open(STATUS, "w").close()
    import setup_aetherwild
    import apply_world_v2
    import import_fab_creatures
    results = [
        step("ouverture / creation du niveau", open_level),
        step("terrain 8 km depuis la heightmap", terrain),
        step("materiaux, import des modeles, ciel, eau, post-process", lambda: setup_aetherwild.run()),
        step("carte v2 (vegetation, lave, materiaux)", lambda: apply_world_v2.run()),
    ]
    if has_fab_creatures():
        results.append(step("creatures Fab (ex. Rampage)", lambda: import_fab_creatures.run()))
    else:
        log("aucun pack de creatures Fab dans le projet (etape ignoree)")
    results.append(step("sauvegarde", save))
    log("RESULTAT : %s" % ("SUCCES" if all(results) else "ECHEC PARTIEL"))
    if quit_after:
        unreal.SystemLibrary.quit_editor()


if __name__ == "__main__":
    run(quit_after="-noquit" not in sys.argv)
