// AETHERWILD - Le dresseur (joueur).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AetherTypes.h"
#include "AetherPlayerCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;
class UCreatureCollectionComponent;
class UStaticMeshComponent;
class UAnimSequence;
class ACreature;

UCLASS()
class AETHERWILD_API AAetherPlayerCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AAetherPlayerCharacter();
	virtual void Tick(float DeltaSeconds) override;

	// ---------- Actions appelees par le PlayerController ----------
	void Move(const FVector2D& Input);
	void Look(const FVector2D& Input);
	void SetSprint(bool bOn);
	void ToggleSneak();
	void SetAiming(bool bOn);
	void PrimaryAction();                  // clic gauche : lancer une capsule (en visee) / ordre d'attaque
	void CommandAbility(int32 Slot);       // 1..4
	void CommandUltimate();                // R
	void ToggleCompanion();                // Q : sortir / rentrer
	void CycleParty(int32 Direction);      // molette
	void CycleCapsule();                   // T
	void ToggleMount();                    // E
	void Interact();                       // F : sanctuaire
	void UsePotion();                      // H
	void CycleTarget();                    // Tab
	void ChooseStarter(int32 Index);       // 1..3 au debut du jeu
	void SaveProgress();
	bool LoadProgress();

	// ---------- Evenements de jeu ----------
	void ReceiveCreatureDamage(float Damage, ACreature* From);
	void OnWildDefeated(ACreature* Wild, int32 XP);
	void OnCompanionFainted(ACreature* Companion);
	void OnCaptureStarted(ACreature* Target, float Chance);
	void OnCaptureSuccess(ACreature* Target, ECapsuleTier Tier);
	void OnCaptureFailed(ACreature* Target);
	void RequestEvolution(ACreature* Companion);
	void Notify(const FString& Message, const FLinearColor& Color = FLinearColor::White);
	void Dismount();

	// ---------- Accesseurs ----------
	UCreatureCollectionComponent* GetCollection() const { return Collection; }
	ACreature* GetActiveCompanion() const;
	ACreature* GetMount() const { return Mount.Get(); }
	ACreature* GetLockedTarget() const { return LockedTarget.Get(); }
	ACreature* GetHoveredCreature() const { return HoveredCreature.Get(); }
	AActor* GetAimTarget() const;
	FVector GetAimPoint() const;
	bool IsRiding() const { return Mount.IsValid(); }
	bool IsAiming() const { return bAiming; }
	bool IsSneaking() const { return bSneaking; }
	bool IsDowned() const { return bDowned; }
	bool IsSwimming() const { return bSwimming; }
	bool NeedsStarter() const { return bNeedsStarter; }
	int32 GetTamerLevel() const;
	float GetHP() const { return HP; }
	float GetMaxHP() const { return MaxHP; }
	float GetCaptureChancePreview(FString& OutReason) const;
	bool IsNearShrine() const;
	float GetLastCaptureChance() const { return LastCaptureChance; }

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<USpringArmComponent> CameraBoom;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UCameraComponent> FollowCamera;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UCreatureCollectionComponent> Collection;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UStaticMeshComponent> FallbackBody;

	FVector RespawnLocation = FVector::ZeroVector;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

private:
	void SetupVisuals();
	void UpdateWater(float Dt);
	void UpdateAnimation();
	void UpdateHover(float Dt);
	void PlayAnim(FName Key, bool bLoop, float Rate = 1.f);
	void ThrowCapsule();
	void Respawn();
	void GiveStarterIfNeeded();
	float SeaLevel() const;

	UPROPERTY() TMap<FName, TObjectPtr<UAnimSequence>> Anims;

	TWeakObjectPtr<ACreature> Mount;
	TWeakObjectPtr<ACreature> LockedTarget;
	TWeakObjectPtr<ACreature> HoveredCreature;
	float HP = 100.f;
	float MaxHP = 100.f;
	float RegenDelay = 0.f;
	float LastThrowTime = -10.f;
	float ThrowAnimEnd = 0.f;
	float LastCaptureChance = 0.f;
	float HoverTimer = 0.f;
	float AutoSaveTimer = 0.f;
	bool bAiming = false;
	bool bSprinting = false;
	bool bSneaking = false;
	bool bSwimming = false;
	bool bDowned = false;
	bool bNeedsStarter = false;
	bool bUsesAnimBlueprint = false;
	FName CurrentAnim;
	float DefaultArmLength = 420.f;
};
