// AETHERWILD - Effets visuels de capacites (explosions lumineuses) et projectiles.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AetherTypes.h"
#include "AbilityEffects.generated.h"

class UStaticMeshComponent;
class UPointLightComponent;
class UMaterialInstanceDynamic;
class ACreature;

/** Sphere lumineuse qui grandit puis s'estompe. Utilise M_AetherGlow (cree par le script d'installation). */
UCLASS()
class AETHERWILD_API AAetherVfx : public AActor
{
	GENERATED_BODY()

public:
	AAetherVfx();
	virtual void Tick(float DeltaSeconds) override;

	static AAetherVfx* SpawnBurst(UWorld* World, const FVector& Location, const FLinearColor& Color, float Radius, float Duration);
	static UMaterialInterface* GetGlowMaterial();

	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Sphere;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UPointLightComponent> Light;

private:
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> MID;
	FLinearColor Color = FLinearColor::White;
	float Radius = 100.f;
	float Duration = 0.5f;
	float Age = 0.f;
};

/** Projectile a tete chercheuse lance par une creature. */
UCLASS()
class AETHERWILD_API AAbilityProjectile : public AActor
{
	GENERATED_BODY()

public:
	AAbilityProjectile();
	virtual void Tick(float DeltaSeconds) override;

	static AAbilityProjectile* Launch(ACreature* Owner, const FVector& Start, AActor* Target, const FVector& Direction, const FAbilityDef& Ability);

	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Sphere;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UPointLightComponent> Light;

private:
	void Impact(AActor* Victim);

	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> MID;
	TWeakObjectPtr<ACreature> Caster;
	TWeakObjectPtr<AActor> Target;
	FAbilityDef Ability;
	FVector Velocity = FVector::ZeroVector;
	float Age = 0.f;
	float Speed = 2400.f;
};
