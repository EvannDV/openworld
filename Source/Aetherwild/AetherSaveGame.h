// AETHERWILD - Sauvegarde.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SaveGame.h"
#include "AetherTypes.h"
#include "AetherSaveGame.generated.h"

UCLASS()
class AETHERWILD_API UAetherSaveGame : public USaveGame
{
	GENERATED_BODY()

public:
	UPROPERTY() TArray<FCreatureInstance> Party;
	UPROPERTY() TArray<FCreatureInstance> Box;
	UPROPERTY() TArray<int32> Capsules;
	UPROPERTY() int32 Potions = 0;
	UPROPERTY() int32 Coins = 0;
	UPROPERTY() int32 TamerXP = 0;
	UPROPERTY() TArray<FName> Seen;
	UPROPERTY() TArray<FName> Caught;
	UPROPERTY() FVector PlayerLocation = FVector::ZeroVector;
	UPROPERTY() FVector RespawnLocation = FVector::ZeroVector;
	UPROPERTY() float TimeOfDay = 9.f;
	UPROPERTY() EWeatherType Weather = EWeatherType::Clear;
};
