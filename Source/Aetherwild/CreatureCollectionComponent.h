// AETHERWILD - Collection du dresseur : equipe (poche, 6 micro-capsules), stockage (Sanctuaire), objets.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "AetherTypes.h"
#include "CreatureCollectionComponent.generated.h"

class ACreature;
class AAetherPlayerCharacter;

UCLASS(ClassGroup = (Aether), meta = (BlueprintSpawnableComponent))
class AETHERWILD_API UCreatureCollectionComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UCreatureCollectionComponent();

	static constexpr int32 MaxParty = 6;

	/** Creatures en poche (micro-capsules). */
	UPROPERTY(BlueprintReadOnly, SaveGame) TArray<FCreatureInstance> Party;
	/** Creatures envoyees au Sanctuaire (stockage illimite). */
	UPROPERTY(BlueprintReadOnly, SaveGame) TArray<FCreatureInstance> Box;

	UPROPERTY(BlueprintReadOnly, SaveGame) TArray<int32> Capsules;   // index = ECapsuleTier
	UPROPERTY(BlueprintReadOnly, SaveGame) int32 Potions = 3;
	UPROPERTY(BlueprintReadOnly, SaveGame) int32 Coins = 100;
	UPROPERTY(BlueprintReadOnly, SaveGame) int32 TamerXP = 0;
	UPROPERTY(BlueprintReadOnly, SaveGame) TSet<FName> Seen;
	UPROPERTY(BlueprintReadOnly, SaveGame) TSet<FName> Caught;

	UPROPERTY(BlueprintReadOnly) int32 SelectedSlot = 0;
	UPROPERTY(BlueprintReadOnly) ECapsuleTier SelectedCapsule = ECapsuleTier::Micro;

	// --- Equipe / compagnon ---
	/** Ajoute une creature capturee. bOutToBox = vrai si la poche etait pleine. */
	bool AddCreature(const FCreatureInstance& Inst, bool& bOutToBox);
	ACreature* GetActiveCompanion() const { return ActiveCompanion.Get(); }
	int32 GetActiveIndex() const;
	ACreature* Deploy(int32 Slot);
	void Recall(bool bInstant = false);
	ACreature* ToggleDeploy();
	void SelectNext(int32 Direction);
	void SyncFromCompanion(const FCreatureInstance& Data);
	FCreatureInstance* FindByGuid(const FGuid& Guid, bool* bOutInBox = nullptr);

	// --- Objets ---
	int32 GetCapsuleCount(ECapsuleTier T) const { return Capsules.IsValidIndex((int32)T) ? Capsules[(int32)T] : 0; }
	bool ConsumeCapsule(ECapsuleTier T);
	void AddCapsules(ECapsuleTier T, int32 N);
	void CycleCapsule();
	bool UsePotion();
	void HealAll();

	// --- Dresseur ---
	int32 GetTamerLevel() const { return 1 + FMath::FloorToInt(FMath::Sqrt(TamerXP / 60.f)); }
	void AddTamerXP(int32 XP);

	// --- Sanctuaire (ecran de stockage) ---
	bool MovePartyToBox(int32 PartyIndex);
	bool MoveBoxToParty(int32 BoxIndex);
	bool Release(bool bFromBox, int32 Index);
	void Evolve(const FGuid& Guid, FName NewSpecies);

private:
	AAetherPlayerCharacter* GetTamer() const;
	TWeakObjectPtr<ACreature> ActiveCompanion;
	FGuid ActiveGuid;
};
