// AETHERWILD - Sanctuaire : soigne l'equipe, recharge les capsules, sauvegarde, point de reapparition.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AetherShrine.generated.h"

class UStaticMeshComponent;
class UPointLightComponent;

UCLASS()
class AETHERWILD_API AAetherShrine : public AActor
{
	GENERATED_BODY()

public:
	AAetherShrine();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Base;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Crystal;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UPointLightComponent> Light;

private:
	float Phase = 0.f;
};
