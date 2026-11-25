// AETHERWILD - Types de base partages par tout le jeu.
#pragma once

#include "CoreMinimal.h"
#include "AetherTypes.generated.h"

AETHERWILD_API DECLARE_LOG_CATEGORY_EXTERN(LogAether, Log, All);

/** Les 9 elements. La table d'efficacite est dans Aether::Effectiveness(). */
UENUM(BlueprintType)
enum class EAetherElement : uint8
{
	Neutral, Fire, Water, Nature, Stone, Storm, Frost, Shadow, Light
};

UENUM(BlueprintType)
enum class EAetherRarity : uint8
{
	Common, Uncommon, Rare, Epic, Legendary
};

/** Forme d'une capacite : determine comment elle est executee. */
UENUM(BlueprintType)
enum class EAbilityShape : uint8
{
	Melee,       // coup au contact devant soi
	Projectile,  // projectile a tete chercheuse
	Nova,        // explosion de zone autour de soi
	Dash,        // charge vers la cible
	Buff,        // augmente l'attaque temporairement
	Heal         // soin
};

UENUM(BlueprintType)
enum class EAetherStatus : uint8
{
	None,
	Burn,     // degats sur la duree
	Soaked,   // ralenti, vulnerable a la Foudre
	Rooted,   // immobilise (peut encore attaquer)
	Stunned,  // ne peut plus agir
	Frozen,   // ne peut plus agir, brise par le Feu
	Blinded,  // precision divisee par deux
	Asleep    // ne peut plus agir, se reveille si frappe
};

UENUM(BlueprintType)
enum class EDayPhase : uint8
{
	Any, Day, Night, Twilight
};

UENUM(BlueprintType)
enum class EWeatherType : uint8
{
	Clear, Cloudy, Rain, Storm, Fog, Snow
};

UENUM(BlueprintType)
enum class ETemperament : uint8
{
	Docile,       // ignore le joueur, se defend si attaque
	Skittish,     // fuit a l'approche
	Territorial,  // attaque si on s'approche trop
	Aggressive    // attaque a vue
};

UENUM(BlueprintType)
enum class EMovementStyle : uint8
{
	Ground, Flying, Swimming, Amphibious
};

/** Capsules de capture (les "micro-box" qu'on garde en poche). */
UENUM(BlueprintType)
enum class ECapsuleTier : uint8
{
	Micro, Ultra, Prism
};

USTRUCT(BlueprintType)
struct FAetherStats
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) float MaxHP = 50.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) float Attack = 10.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) float Defense = 10.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) float Spirit = 10.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) float Speed = 10.f;
};

USTRUCT(BlueprintType)
struct FAbilityDef
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly) FName Id;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FString DisplayName;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FString Description;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) EAetherElement Element = EAetherElement::Neutral;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) EAbilityShape Shape = EAbilityShape::Melee;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float Power = 40.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float Accuracy = 0.95f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float Cooldown = 2.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float Range = 250.f;      // cm
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float Radius = 250.f;     // cm (Nova / impact)
	UPROPERTY(EditAnywhere, BlueprintReadOnly) bool bSpecial = false;    // utilise Esprit au lieu d'Attaque
	UPROPERTY(EditAnywhere, BlueprintReadOnly) bool bUltimate = false;   // coup special : jauge de Resonance pleine
	UPROPERTY(EditAnywhere, BlueprintReadOnly) EAetherStatus Status = EAetherStatus::None;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float StatusChance = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float StatusDuration = 4.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float BuffAmount = 0.f;   // Buff : +x% attaque, Heal : % PV
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float VfxScale = 1.f;
};

/** Conditions speciales pour qu'une espece accepte d'etre capturee. */
USTRUCT(BlueprintType)
struct FCaptureRules
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly) EDayPhase Phase = EDayPhase::Any;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<EWeatherType> Weathers;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) EAetherElement WeakenedBy = EAetherElement::Neutral;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float MaxHealthFraction = 1.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) int32 MinTamerLevel = 1;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) bool bRequiresStatus = false;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FString Hint;
};

USTRUCT(BlueprintType)
struct FLearnEntry
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadOnly) int32 Level = 1;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FName Ability;
};

USTRUCT(BlueprintType)
struct FSpeciesDef
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly) FName Id;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FString DisplayName;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FString Description;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) EAetherElement Element1 = EAetherElement::Neutral;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) EAetherElement Element2 = EAetherElement::Neutral;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) EAetherRarity Rarity = EAetherRarity::Common;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FAetherStats BaseStats;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float CatchRate = 0.5f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) int32 BaseXP = 40;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<FName> Biomes;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) EDayPhase SpawnPhase = EDayPhase::Any;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<EWeatherType> SpawnWeathers;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) int32 MinLevel = 2;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) int32 MaxLevel = 8;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float SizeMeters = 1.f;   // plus grande dimension du modele
	UPROPERTY(EditAnywhere, BlueprintReadOnly) EMovementStyle Movement = EMovementStyle::Ground;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) bool bRideable = false;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) bool bEmitsLight = false;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float WalkSpeed = 250.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float RunSpeed = 600.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) ETemperament Temperament = ETemperament::Docile;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<FLearnEntry> Learnset;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FName Ultimate;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FName EvolvesTo;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) int32 EvolveLevel = 0;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FString AssetFolder;
	// --- Assets realistes (optionnels, prioritaires sur AssetFolder) : voir "visual" dans species.json ---
	/** Blueprint enfant de ACreature (fourrure Groom, materiaux, Niagara, AnimBP...). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FString BlueprintPath;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FString MeshPath;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FString AnimBlueprintPath;
	/** Idle/Walk/Run/Attack/Fly/Swim -> chemin d'AnimSequence. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly) TMap<FName, FString> AnimPaths;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) bool bOverrideYaw = false;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) float MeshYaw = -90.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FName SaddleSocket = TEXT("saddle");
	/** Si vrai, la taille du modele n'est pas normalisee sur SizeMeters (modele deja a l'echelle). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly) bool bKeepMeshScale = false;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FLinearColor PrimaryColor = FLinearColor::Gray;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FLinearColor AccentColor = FLinearColor::White;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<FString> Aptitudes;
	UPROPERTY(EditAnywhere, BlueprintReadOnly) FCaptureRules Capture;

	bool HasElement(EAetherElement E) const { return Element1 == E || (Element2 == E && E != EAetherElement::Neutral); }
	bool CanFly() const { return Movement == EMovementStyle::Flying; }
	bool CanSwim() const { return Movement == EMovementStyle::Swimming || Movement == EMovementStyle::Amphibious; }
	bool IsAquaticOnly() const { return Movement == EMovementStyle::Swimming; }
};

/** Une creature possedee (ou sauvage) : c'est ce qui est sauvegarde et range dans les capsules. */
USTRUCT(BlueprintType)
struct FCreatureInstance
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) FGuid Guid;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) FName SpeciesId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) FString Nickname;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) int32 Level = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) int32 XP = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) float CurrentHP = -1.f;   // -1 = plein
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) TArray<FName> Abilities;  // 4 max
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) FAetherStats Potential;   // multiplicateurs 0.9 - 1.15
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) bool bPrismatic = false;  // variante chromatique tres rare
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame) int32 Bond = 0;

	bool IsValid() const { return !SpeciesId.IsNone(); }
};

namespace Aether
{
	AETHERWILD_API float Effectiveness(EAetherElement Attack, EAetherElement Defender);
	AETHERWILD_API float EffectivenessVs(EAetherElement Attack, const FSpeciesDef& Defender);
	AETHERWILD_API FAetherStats ComputeStats(const FSpeciesDef& Species, const FCreatureInstance& Inst);
	AETHERWILD_API int32 XPForNextLevel(int32 Level);
	AETHERWILD_API int32 RarityWeight(EAetherRarity Rarity);

	AETHERWILD_API FString ElementName(EAetherElement E);
	AETHERWILD_API FLinearColor ElementColor(EAetherElement E);
	AETHERWILD_API FString RarityName(EAetherRarity R);
	AETHERWILD_API FLinearColor RarityColor(EAetherRarity R);
	AETHERWILD_API FString StatusName(EAetherStatus S);
	AETHERWILD_API FString PhaseName(EDayPhase P);
	AETHERWILD_API FString WeatherName(EWeatherType W);
	AETHERWILD_API FString CapsuleName(ECapsuleTier T);
	AETHERWILD_API float CapsuleMultiplier(ECapsuleTier T);
	AETHERWILD_API FLinearColor CapsuleColor(ECapsuleTier T);
	AETHERWILD_API FString DisplayNameOf(const FCreatureInstance& Inst, const FSpeciesDef* Species);
}
