// AETHERWILD - Classe parente pour les Animation Blueprints (joueur MetaHuman, creatures realistes).
// Dans l'AnimBP : Class Settings > Parent Class = AetherAnimInstance, puis utilise les variables
// ci-dessous dans une State Machine / Blend Space (Idle <-> Walk <-> Run, Swim, Fly, Ride...).
// Les attaques/lancers sont joues en montage sur le slot "DefaultSlot" : ajoute un noeud Slot 'DefaultSlot'
// juste avant Output Pose.
#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "AetherAnimInstance.generated.h"

UCLASS()
class AETHERWILD_API UAetherAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;

	/** Vitesse horizontale (cm/s). */
	UPROPERTY(BlueprintReadOnly, Category = "Aether") float Speed = 0.f;
	/** Vitesse normalisee : 0 arret, 1 marche, 2 course. Pratique pour un Blend Space 1D. */
	UPROPERTY(BlueprintReadOnly, Category = "Aether") float Gait = 0.f;
	/** Direction du mouvement relative au regard (-180..180). */
	UPROPERTY(BlueprintReadOnly, Category = "Aether") float Direction = 0.f;
	UPROPERTY(BlueprintReadOnly, Category = "Aether") float VerticalSpeed = 0.f;
	UPROPERTY(BlueprintReadOnly, Category = "Aether") bool bIsInAir = false;
	UPROPERTY(BlueprintReadOnly, Category = "Aether") bool bIsSwimming = false;
	UPROPERTY(BlueprintReadOnly, Category = "Aether") bool bIsFlying = false;
	/** Joueur : assis sur une monture. Creature : chevauchee. */
	UPROPERTY(BlueprintReadOnly, Category = "Aether") bool bIsRiding = false;
	UPROPERTY(BlueprintReadOnly, Category = "Aether") bool bIsAiming = false;
	UPROPERTY(BlueprintReadOnly, Category = "Aether") bool bIsFainted = false;
	UPROPERTY(BlueprintReadOnly, Category = "Aether") bool bInCombat = false;
	/** Rotation de la tete vers la cible (look-at), en degres. */
	UPROPERTY(BlueprintReadOnly, Category = "Aether") float LookYaw = 0.f;

private:
	float SmoothedSpeed = 0.f;
};
