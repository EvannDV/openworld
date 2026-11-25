// AETHERWILD - Mode de jeu : instancie le monde (sanctuaires, zones de creatures, vegetation, eau, ciel).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "AetherGameMode.generated.h"

UCLASS()
class AETHERWILD_API AAetherGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AAetherGameMode();
	virtual void StartPlay() override;
	virtual UClass* GetDefaultPawnClassForController_Implementation(AController* InController) override;

	/** Cree l'eclairage/ciel si le niveau n'en a pas (permet de jouer meme sans avoir lance le script d'installation). */
	UPROPERTY(EditDefaultsOnly, Category = "Aether") bool bSpawnFallbackSky = true;

private:
	void SpawnWorldContent();
	void SpawnFallbackSky();
	void SpawnWaterIfMissing();
};
