// AETHERWILD - Micro-capsule de capture lancee par le dresseur.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AetherTypes.h"
#include "CaptureCapsule.generated.h"

class USphereComponent;
class UStaticMeshComponent;
class UProjectileMovementComponent;
class UPointLightComponent;
class ACreature;
class AAetherPlayerCharacter;

UCLASS()
class AETHERWILD_API ACaptureCapsule : public AActor
{
	GENERATED_BODY()

public:
	ACaptureCapsule();
	virtual void Tick(float DeltaSeconds) override;

	void Throw(AAetherPlayerCharacter* InThrower, ECapsuleTier InTier, const FVector& Velocity);

	/** Probabilite finale de capture (0 si une condition speciale n'est pas remplie, OutReason explique pourquoi). */
	static float ComputeCaptureChance(const ACreature* Target, ECapsuleTier Tier, int32 TamerLevel, FString& OutReason);

	UPROPERTY(VisibleAnywhere) TObjectPtr<USphereComponent> Collision;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Shell;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Band;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UPointLightComponent> Light;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UProjectileMovementComponent> Movement;

private:
	UFUNCTION() void OnHit(UPrimitiveComponent* HitComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit);
	void StartCapture(ACreature* Target);
	void DoShake();
	void Finish(bool bSuccess);

	TWeakObjectPtr<AAetherPlayerCharacter> Thrower;
	TWeakObjectPtr<ACreature> Captive;
	ECapsuleTier Tier = ECapsuleTier::Micro;
	float Chance = 0.f;
	int32 Shakes = 0;
	float ShakeAnim = 0.f;
	float IdleTime = 0.f;
	bool bCapturing = false;
	bool bDone = false;
	FTimerHandle ShakeTimer;
};
