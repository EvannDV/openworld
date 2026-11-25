// AETHERWILD - Base de donnees des especes / capacites / monde, chargee depuis Content/Data/*.json
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "AetherTypes.h"
#include "Animation/AnimInstance.h"
#include "CreatureDatabase.generated.h"

class USkeletalMesh;
class UAnimInstance;
class ACreature;
class APawn;
class UAnimSequence;
class FJsonObject;

/** Modele + animations d'une espece, resolus une seule fois via l'Asset Registry. */
USTRUCT()
struct FCreatureVisuals
{
	GENERATED_BODY()

	UPROPERTY() TObjectPtr<USkeletalMesh> Mesh = nullptr;
	UPROPERTY() TMap<FName, TObjectPtr<UAnimSequence>> Anims;   // Idle, Walk, Run, Attack, Fly, Swim, Throw, Ride
	/** Animation Blueprint (transitions fluides, blend spaces, IK...). Si defini, remplace la lecture directe des cycles. */
	UPROPERTY() TSubclassOf<UAnimInstance> AnimClass;
	bool bResolved = false;
};

struct FAetherSpawnerDef
{
	FName Biome;
	FVector Location = FVector::ZeroVector;
	float Radius = 4000.f;
	int32 MaxAlive = 4;
};

UCLASS()
class AETHERWILD_API UCreatureDatabase : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	static UCreatureDatabase* Get(const UObject* WorldContext);

	const FSpeciesDef* FindSpecies(FName Id) const { return Species.Find(Id); }
	const FAbilityDef* FindAbility(FName Id) const { return Abilities.Find(Id); }
	const TArray<FName>& GetSpeciesOrder() const { return SpeciesOrder; }

	/** Cree une instance (stats aleatoires, attaques apprises jusqu'a ce niveau). */
	FCreatureInstance MakeInstance(FName SpeciesId, int32 Level, FRandomStream& Rng) const;

	/** Apprend les capacites du niveau atteint. Renvoie les noms appris. */
	TArray<FName> LearnAbilitiesForLevel(FCreatureInstance& Inst, int32 Level) const;

	/** Tire une espece selon le biome, l'heure, la meteo et la rarete. */
	FName RollSpecies(FName Biome, EDayPhase Phase, EWeatherType Weather, FRandomStream& Rng, int32& OutLevel) const;

	/** Mesh + animations d'une espece (chemins dans species.json -> assetFolder). */
	const FCreatureVisuals& GetVisuals(FName SpeciesId);
	const FCreatureVisuals& GetVisualsForFolder(const FString& Folder);
	const FCreatureVisuals& GetPlayerVisuals();

	/** Classe a faire apparaitre pour une espece : Blueprint "visual.blueprint" ou ACreature. */
	UClass* GetCreatureClass(FName SpeciesId) const;
	/** Pion du joueur : Blueprint "player.blueprint" (ex. BP_Tamer avec un MetaHuman) ou AAetherPlayerCharacter. */
	UClass* GetPlayerPawnClass() const;

	// Visuel du joueur (species.json -> "player")
	FString PlayerBlueprintPath;
	FString PlayerMeshPath;
	FString PlayerAnimBlueprintPath;
	TMap<FName, FString> PlayerAnimPaths;
	float PlayerMeshYaw = -90.f;
	float PlayerHeightCm = 176.f;

	// --- Donnees du monde (world.json, genere par Tools/Terrain) ---
	float SeaLevelZ = 0.f;
	FVector PlayerStart = FVector(0, 0, 2000);
	FVector2D VolcanoXY = FVector2D::ZeroVector;
	TArray<FVector> ShrineLocations;
	TArray<FAetherSpawnerDef> SpawnerDefs;
	TSharedPtr<FJsonObject> ScatterConfig;
	FString PlayerAssetFolder = TEXT("/Game/Aetherwild/Characters/Tamer");
	float MeshYawOffset = -90.f;
	TArray<FName> StarterSpecies;

	static FString DataDir();

private:
	void ResolveExplicitVisuals(FCreatureVisuals& V, const FString& MeshPath, const FString& AnimBPPath, const TMap<FName, FString>& AnimPaths);
	void LoadAbilities();
	void LoadSpecies();
	void LoadWorld();

	TMap<FName, FSpeciesDef> Species;
	TArray<FName> SpeciesOrder;
	TMap<FName, FAbilityDef> Abilities;

	UPROPERTY() TMap<FString, FCreatureVisuals> VisualCache;
};
