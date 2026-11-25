// AETHERWILD - Creature (sauvage, compagnon ou monture).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AetherTypes.h"
#include "Creature.generated.h"

class AAetherPlayerCharacter;
class ACreatureSpawner;
class UCameraComponent;
class USpringArmComponent;
class UPointLightComponent;
class UAnimSequence;
class AController;

UENUM(BlueprintType)
enum class ECreatureMode : uint8
{
	Wild, Companion, Ridden
};

UENUM(BlueprintType)
enum class ECreatureBrain : uint8
{
	Idle, Wander, Flee, Fight, Follow, Return, Fainted, Captured
};

UCLASS()
class AETHERWILD_API ACreature : public ACharacter
{
	GENERATED_BODY()

public:
	ACreature();

	virtual void Tick(float DeltaSeconds) override;

	/** A appeler juste apres le spawn (SpawnActorDeferred puis FinishSpawning, ou juste apres SpawnActor). */
	void InitCreature(const FCreatureInstance& InData, ECreatureMode InMode, AAetherPlayerCharacter* InTamer = nullptr);

	// ---------- Infos ----------
	const FSpeciesDef& GetSpecies() const { return Species; }
	const FCreatureInstance& GetData() const { return Data; }
	FCreatureInstance& GetMutableData() { return Data; }
	const FAetherStats& GetStats() const { return Stats; }
	ECreatureMode GetMode() const { return Mode; }
	ECreatureBrain GetBrain() const { return Brain; }
	AAetherPlayerCharacter* GetTamer() const;
	AAetherPlayerCharacter* GetRider() const;
	float GetHP() const { return Data.CurrentHP; }
	float GetHPFraction() const { return Stats.MaxHP > 0 ? Data.CurrentHP / Stats.MaxHP : 0.f; }
	bool IsFainted() const { return Brain == ECreatureBrain::Fainted || Data.CurrentHP <= 0.f; }
	bool IsBeingCaptured() const { return Brain == ECreatureBrain::Captured; }
	bool IsHostileTo(const AActor* Other) const;
	bool IsWild() const { return Mode == ECreatureMode::Wild; }
	float GetBodyRadius() const;
	FString GetDisplayName() const;
	int32 GetCaptureEscapes() const { return CaptureEscapes; }
	AActor* GetCombatTarget() const { return CombatTarget.Get(); }

	// ---------- Combat ----------
	UPROPERTY(BlueprintReadOnly) float Resonance = 0.f;              // 0..100 : jauge du coup special
	UPROPERTY(BlueprintReadOnly) EAetherStatus Status = EAetherStatus::None;
	UPROPERTY(BlueprintReadOnly) float StatusTimeLeft = 0.f;
	UPROPERTY(BlueprintReadOnly) EAetherElement LastHitElement = EAetherElement::Neutral;

	bool TryUseAbility(FName AbilityId, AActor* Target);
	bool IsAbilityReady(FName AbilityId) const;
	float GetCooldownRemaining(FName AbilityId) const;
	float GetCooldownFraction(FName AbilityId) const;
	bool CanAct() const;
	void SetCombatTarget(AActor* Target, FName PreferredAbility = NAME_None);
	void ClearCombatTarget();
	void NotifyAttackedBy(AActor* Attacker);
	void ApplyStatus(EAetherStatus NewStatus, float Duration);
	void ReceiveHit(ACreature* Attacker, const FAbilityDef& Ability, float Damage, bool bCrit, float Effectiveness);
	void ReceiveRawDamage(float Damage, AActor* Source);
	void Heal(float Amount);
	void FullRestore();

	/** Calcule et applique un coup (degats, precision, statut, resonance). Gere creature ET joueur comme cible. */
	static void ResolveHit(ACreature* Attacker, AActor* Victim, const FAbilityDef& Ability, float PowerScale = 1.f);

	// ---------- Capture ----------
	void BeginCaptureAbsorb();
	void EndCaptureEscape();

	// ---------- Monture ----------
	bool CanBeRidden() const;
	void OnMounted(AAetherPlayerCharacter* InRider);
	void OnDismounted();
	void RiderMove(const FVector2D& Input);
	void RiderVertical(float Value);
	void RiderJump();
	void RiderSprint(bool bOn) { bRiderSprint = bOn; }
	FName GetSaddleSocket() const { return Species.SaddleSocket; }
	bool IsSwimming() const { return bSwimming; }
	bool IsFlyingNow() const;
	USkeletalMeshComponent* GetVisualMesh() const;
	TWeakObjectPtr<AController> StoredAIController;

	// ---------- Progression ----------
	void GainXP(int32 Amount);

	// ---------- Composants ----------
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<USpringArmComponent> CameraBoom;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UCameraComponent> RideCamera;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UStaticMeshComponent> FallbackBody;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UPointLightComponent> Glow;

	TWeakObjectPtr<ACreatureSpawner> HomeSpawner;
	FVector HomeLocation = FVector::ZeroVector;

protected:
	virtual void BeginPlay() override;
	virtual void Landed(const FHitResult& Hit) override;

private:
	void SetupVisuals();
	void SetupMovement();
	void UpdateStatus(float Dt);
	void UpdateWater(float Dt);
	void UpdateFlightHover(float Dt);
	void UpdateWild(float Dt);
	void UpdateCompanion(float Dt);
	void UpdateFight(float Dt);
	void UpdateAnimation(float Dt);
	void UpdateFaint(float Dt);
	void UpdateGlow();
	bool MoveTowards(const FVector& Dest, float SpeedScale, float AcceptRadius);
	void FaceTowards(const FVector& Point, float Dt);
	bool PickWanderDestination();
	FName ChooseAbility(AActor* Target, float Distance) const;
	void ExecuteAbility(const FAbilityDef& Ability, AActor* Target);
	void Faint(AActor* Killer);
	void PlayAnim(FName Key, bool bLoop, float Rate = 1.f);
	float GroundHeightAt(const FVector& Location, bool& bHit) const;
	float SeaLevel() const;
	bool IsLocationWater(const FVector& Location) const;
	void SyncToTamer();
	float Now() const;
	void SpawnFloatingText(const FString& Text, const FLinearColor& Color) const;

	UPROPERTY() FCreatureInstance Data;
	UPROPERTY() FSpeciesDef Species;
	UPROPERTY() FAetherStats Stats;
	UPROPERTY() ECreatureMode Mode = ECreatureMode::Wild;
	UPROPERTY() ECreatureBrain Brain = ECreatureBrain::Idle;
	UPROPERTY() TMap<FName, TObjectPtr<UAnimSequence>> Anims;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> FallbackMID;

	TWeakObjectPtr<AAetherPlayerCharacter> Tamer;
	TWeakObjectPtr<AAetherPlayerCharacter> Rider;
	TWeakObjectPtr<AActor> CombatTarget;
	TWeakObjectPtr<AActor> LastAttacker;
	FName PendingAbility;
	TMap<FName, float> CooldownEnd;
	float GlobalCooldownEnd = 0.f;
	float AttackBuff = 1.f;
	float AttackBuffEnd = 0.f;
	float AttackAnimEnd = 0.f;
	float BrainTimer = 0.f;
	float PerceptionTimer = 0.f;
	float GlowTimer = 0.f;
	float LastCombatTime = -100.f;
	float FaintTime = 0.f;
	float BurnTick = 0.f;
	float HoverHeight = 500.f;
	float CachedGroundZ = 0.f;
	float GroundTraceTimer = 0.f;
	FVector WanderTarget = FVector::ZeroVector;
	bool bHasWanderTarget = false;
	bool bSwimming = false;
	bool bUsesAnimBlueprint = false;
	bool bRiderSprint = false;
	bool bRiderFlying = false;
	float RiderVerticalInput = 0.f;
	int32 CaptureEscapes = 0;
	FName CurrentAnim;
	float MeshBaseScale = 1.f;
	float HalfHeight = 50.f;
	TSet<TWeakObjectPtr<ACreature>> Participants;   // compagnons ayant combattu cette creature (XP)
};
