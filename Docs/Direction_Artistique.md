# Aetherwild : direction artistique réaliste

Objectif : des créatures **crédibles biologiquement**, comme si elles existaient vraiment. On part d'une anatomie animale
réelle, qu'on modifie par l'élément (feu, givre, foudre…). Les détails magiques restent **subtils et physiques** :
bioluminescence, cristaux minéraux, braises sous la peau. On évite les effets « cartoon ».

## Règles communes

- **Anatomie** : squelette et musculature d'un animal réel de référence (indiqué sur chaque fiche) ; proportions réalistes ;
  poids visible dans la posture.
- **Surfaces** : fourrure en Groom (UE Hair) ou en cartes de poils pour les mammifères ; écailles, plaques ou chitine
  sculptées dans ZBrush ou Blender, avec cartes de déplacement ; peau en *subsurface scattering*.
- **Textures** : PBR en 4K (BaseColor, Normal, ORM), plus une carte d'émission pour la bioluminescence. Usure, saleté,
  cicatrices et variation de teinte.
- **Budget** : environ 60 à 120 k triangles au LOD0 (Nanite pour maillages animés : expérimental depuis UE 5.5) ; 4 LOD ; squelette
  avec os de queue, oreilles, mâchoire et paupières.
- **Animations minimum** : Idle (×2 variantes), Walk, Trot/Run, Turn in place, Attack ×2, Hit, Faint, Roar ;
  plus Fly, Glide et Land pour les volants, Swim pour les aquatiques, et un socket `saddle` pour les montures.
- **Palette** : couleurs naturelles et désaturées ; l'élément n'apparaît qu'en accents.

## Dresseur (joueur)

**MetaHuman** : explorateur de 25 à 35 ans, veste de randonnée technique usée, sac à dos de terrain, ceinture porte-capsules
(6 micro-capsules en verre et métal brossé, avec un liseré lumineux cyan), gants en cuir, bottes de montagne.
Prévoir une variante masculine et une variante féminine.

---

## Fiches créatures

### Braisillon (Feu, commun) : renard des braises
- **Référence** : renard roux (*Vulpes vulpes*), 1,1 m queue comprise.
- **Design** : pelage roux profond, ventre crème ; l'extrémité de la queue n'est pas une flamme cartoon mais des **poils
  incandescents** comme des braises de charbon, avec de petites flammèches qui s'échappent (Niagara). Grandes oreilles
  aux bords noircis par la suie, yeux ambre.
- **Prompt IA 3D** : *photorealistic red fox creature, oversized ears with soot-blackened tips, bushy tail whose tip is made of glowing ember-like fur emitting small sparks, cream belly, amber eyes, natural anatomy, PBR, 4K textures, game-ready*

### Pyrolynx (Feu, rare, monture) : grand félin volcanique
- **Référence** : lynx boréal + puma, 3 m de long, 1,1 m au garrot.
- **Design** : pelage brun-rouge sombre rayé de noir ; une crinière dorsale de longs poils raides dont les pointes
  **rougeoient comme du fer chauffé** ; touffes d'oreilles carbonisées ; traces de lave séchée sur les pattes.
  Harnais de monte en cuir.
- **Prompt** : *photorealistic large lynx-puma hybrid, dark red-brown striped fur, dorsal mane of stiff hairs with glowing red-hot tips like heated iron, charred ear tufts, dried lava crust on paws, muscular, saddle-ready, PBR 4K*

### Ondrelle (Eau, commun) : loutre des rivières
- **Référence** : loutre d'Europe, 1,3 m.
- **Design** : fourrure dense et mouillée (Groom, avec un *wetness mask*), dos bleu-gris ardoise ; de petites **nageoires
  translucides** le long de la colonne, avec des veines bleu clair bioluminescentes.
- **Prompt** : *photorealistic river otter creature, wet slate blue-grey fur, small translucent fins along the spine with faint bioluminescent blue veins, webbed paws, whiskers, PBR*

### Néréon (Eau, rare, monture aquatique)
- **Référence** : léopard de mer + loutre géante, 4 m.
- **Design** : peau lisse de mammifère marin, bleu nuit tacheté ; grandes nageoires dorsales et caudales à membrane
  translucide, avec des **points lumineux comme des photophores** ; vibrisses épaisses ; corps hydrodynamique.
- **Prompt** : *photorealistic sea-leopard otter hybrid, 4 meters long, sleek dark blue spotted skin, translucent dorsal and tail fins with glowing photophores, thick whiskers, aquatic predator, PBR 4K*

### Feuillouve (Nature, commun) : louveteau des mousses
- **Référence** : louveteau gris, 1,2 m.
- **Design** : fourrure mêlée de **mousse vivante et de lichens** sur le dos et les épaules, quelques fougères qui poussent
  sur la nuque, oreilles en forme de feuille de chêne mais poilues.
- **Prompt** : *photorealistic wolf cub creature with living moss and lichen growing on its back and shoulders, small ferns sprouting from the nape, grey-green fur, natural forest animal, PBR*

### Sylvecerf (Nature, rare, monture) : cerf-forêt
- **Référence** : cerf élaphe (wapiti), 2,9 m avec les bois.
- **Design** : bois gigantesques couverts d'écorce, de lierre et de petites feuilles ; quelques **fleurs bioluminescentes**
  au crépuscule ; pelage fauve tacheté de blanc comme un faon adulte.
- **Prompt** : *photorealistic majestic elk, massive antlers covered in bark, ivy and small leaves with a few softly glowing flowers, fawn-colored coat with white spots, forest guardian, PBR 4K*

### Moussibul (Nature, commun)
- **Référence** : hérisson + champignon (amadouvier), 0,65 m.
- **Design** : petit animal rond dont le dos est un **coussin de mousse épaisse** ; une grande fleur rose en sort ;
  petites pattes griffues, museau humide, yeux noirs brillants.
- **Prompt** : *photorealistic small round hedgehog-like creature whose back is a thick cushion of moss with a large pink flower, tiny clawed feet, wet nose, glossy black eyes*

### Galetor (Roche, peu commun) : golem minéral
- **Référence** : gorille (posture) + formation basaltique, 2,3 m.
- **Design** : corps fait de **colonnes de basalte** et de blocs de granit, liés par du lichen ; des fissures laissent
  voir un **magma orange** qui pulse lentement ; les mains sont d'énormes blocs. Pas de visage humain, seulement deux
  braises dans une cavité.
- **Prompt** : *photorealistic rock golem made of basalt columns and granite blocks, gorilla posture, glowing orange magma visible through cracks, lichen, two ember eyes in a dark cavity, PBR 4K*

### Volterelle (Foudre, peu commun)
- **Référence** : guêpier d'Europe, envergure 1 m.
- **Design** : plumage jaune soufre et bleu nuit ; crête de plumes dont les pointes **crépitent d'arcs électriques**.
- **Prompt** : *photorealistic bee-eater bird creature, sulfur yellow and midnight blue plumage, crest feathers with tiny crackling electric arcs, realistic feathers*

### Orajaile (Foudre, épique, monture volante)
- **Référence** : aigle harpie + chauve-souris (structure des ailes), envergure 6 m.
- **Design** : plumage gris-bleu orageux ; des lignes claires sur les ailes **s'illuminent comme des éclairs dans les
  nuages** ; bec massif, serres énormes, crête rigide ; regard perçant.
- **Prompt** : *photorealistic giant harpy eagle storm bird, 6 meter wingspan, storm-grey blue plumage with pale lightning patterns that glow on the wings, massive beak and talons, rigid crest, epic, PBR 4K*

### Grelichon (Givre, commun)
- **Référence** : lagopède / boule de plumes, 0,6 m.
- **Design** : petite créature duveteuse blanche couverte de **givre**, avec des cristaux de glace translucides sur le dos.
- **Prompt** : *photorealistic small fluffy white snow creature, frost on the fur, translucent ice crystals on its back, tiny black eyes, arctic animal*

### Givrelan (Givre, rare, monture)
- **Référence** : élan (orignal), 3 m.
- **Design** : pelage blanc et gris, épais et chargé de neige ; les bois sont en **glace cristalline translucide** à
  réfraction (matériau *refraction*), traversés de lumière bleue ; souffle visible (Niagara).
- **Prompt** : *photorealistic giant moose, thick white-grey snowy fur, antlers made of translucent crystalline ice refracting blue light, frosty breath, PBR 4K*

### Nocthys (Ombre, rare, nocturne)
- **Référence** : panthère des neiges (corps), 1,8 m.
- **Design** : pelage noir mat, avec des rosettes **violettes bioluminescentes** à peine visibles le jour ; yeux réfléchissants
  (tapetum) ; oreilles à pinceaux.
- **Prompt** : *photorealistic black snow leopard, matte black fur with faint violet bioluminescent rosettes, reflective eyes, lynx ear tufts, stealthy, PBR 4K*

### Cendrebuffle (Feu/Roche, monture)
- **Référence** : bison d'Amérique, 2,9 m.
- **Design** : bosse massive couverte de **croûte volcanique craquelée** où rougeoie la lave ; cornes noires et polies ;
  laine sombre et roussie ; vapeur aux naseaux.
- **Prompt** : *photorealistic bison creature with cracked volcanic crust on its hump revealing glowing lava, polished black horns, scorched dark wool, steaming nostrils, PBR 4K*

### Lumiole (Lumière, commun, nocturne)
- **Référence** : ver luisant et papillon de nuit (lucane), 0,5 m.
- **Design** : insecte rond et velu, abdomen qui **luit doucement** en jaune chaud, longues antennes plumeuses,
  ailes translucides repliées.
- **Prompt** : *photorealistic large fuzzy firefly moth creature, softly glowing warm yellow abdomen, feathery antennae, folded translucent wings, macro detail*

### Marévore (Eau/Ombre, légendaire)
- **Référence** : régalec (poisson-ruban) + murène + serpent, 14 m.
- **Design** : corps long et musculeux, peau noir-bleu iridescente, grande crête dorsale rouge-corail translucide ;
  **lignes de photophores** turquoise ; tête de murène avec des cornes recourbées ; yeux sans pupille.
- **Prompt** : *photorealistic legendary sea serpent, 14 meters, oarfish moray eel hybrid, iridescent blue-black skin, long translucent coral-red dorsal crest, rows of turquoise photophores, curved horns, abyssal, PBR 8K*

### Solarion (Lumière/Feu, légendaire)
- **Référence** : faisan doré + aigle royal, envergure 6,7 m.
- **Design** : plumage or pâle et orangé ; longues plumes de queue dont les extrémités **émettent une lumière solaire**
  (pas des flammes), couronne de plumes rigides lumineuses ; regard noble.
- **Prompt** : *photorealistic legendary sun bird, golden pheasant and golden eagle hybrid, pale gold and orange plumage, very long tail feathers with glowing sunlit tips, crown of rigid luminous feathers, majestic, PBR 8K*

---

## Comment les obtenir

| Voie | Qualité | Coût et délai | Pour quoi |
|---|---|---|---|
| **Artiste 3D** (ArtStation, Fiverr, studios freelance) avec ces fiches | ★★★★★ originale | Le plus cher, plusieurs semaines par créature | Créatures principales, légendaires |
| **Packs de créatures sur Fab** (animaux et monstres rigués, animés, en PBR) | ★★★★ réaliste, mais pas unique | Le plus rapide | Base à retoucher : textures, ajouts lumineux |
| **Génération 3D par IA** (avec les prompts ci-dessus) puis rig (AccuRIG, Blender Rigify) | ★★★ variable | Peu cher, quelques heures par créature | Prototypes, créatures communes |
| **MetaHuman** (dans UE 5.6+) | ★★★★★ | Gratuit | Le dresseur et les PNJ |

Une fois un modèle prêt, deux possibilités : renseigne `"visual"` dans `Content/Data/species.json`, ou crée un Blueprint
enfant de `Creature` (voir README, section 8).
