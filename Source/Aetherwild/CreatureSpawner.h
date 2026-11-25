// AETHERWILD - Zone d'apparition de creatures sauvages (un biome, un rayon, une population max).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CreatureSpawner.generated.h"

class ACreature;

UCLASS()
class AETHERWILD_API ACreatureSpawner : public AActor
{
	GENERATED_BODY()

public:
	ACreatureSpawner();
	virtual void Tick(float DeltaSeconds) override;

	/** Plains, Forest, Mountains, Peaks, Volcano, Shore, Water */
	UPROPERTY(EditAnywhere, Category = "Aether") FName Biome = TEXT("Plains");
	UPROPERTY(EditAnywhere, Category = "Aether") float Radius = 4000.f;
	UPROPERTY(EditAnywhere, Category = "Aether") int32 MaxAlive = 4;
	UPROPERTY(EditAnywhere, Category = "Aether") float RespawnDelay = 25.f;
	/** Ne fait apparaitre des creatures que si le joueur est a moins de cette distance (performances). */
	UPROPERTY(EditAnywhere, Category = "Aether") float ActivationDistance = 14000.f;

private:
	void SpawnOne(const FVector& PlayerLoc);
	bool FindSpawnPoint(bool bWaterSpecies, bool bFlying, const FVector& PlayerLoc, FVector& Out) const;

	TArray<TWeakObjectPtr<ACreature>> Alive;
	float Cooldown = 0.f;
	FRandomStream Rng;
};
