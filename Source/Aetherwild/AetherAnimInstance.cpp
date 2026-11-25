#include "AetherAnimInstance.h"

#include "AetherPlayerCharacter.h"
#include "Creature.h"
#include "GameFramework/CharacterMovementComponent.h"

void UAetherAnimInstance::NativeUpdateAnimation(float Dt)
{
	Super::NativeUpdateAnimation(Dt);
	const APawn* Pawn = TryGetPawnOwner();
	if (!Pawn) return;

	const FVector V = Pawn->GetVelocity();
	SmoothedSpeed = FMath::FInterpTo(SmoothedSpeed, V.Size2D(), Dt, 10.f);
	Speed = SmoothedSpeed;
	VerticalSpeed = V.Z;

	const FRotator Facing = Pawn->GetActorRotation();
	if (V.SizeSquared2D() > 25.f)
	{
		Direction = FRotator::NormalizeAxis(V.Rotation().Yaw - Facing.Yaw);
	}

	float WalkSpeed = 250.f, RunSpeed = 650.f;
	if (const ACharacter* Ch = Cast<ACharacter>(Pawn))
	{
		const UCharacterMovementComponent* CMC = Ch->GetCharacterMovement();
		bIsInAir = CMC && CMC->IsFalling();
	}

	if (const ACreature* C = Cast<ACreature>(Pawn))
	{
		WalkSpeed = C->GetSpecies().WalkSpeed;
		RunSpeed = C->GetSpecies().RunSpeed;
		bIsSwimming = C->IsSwimming();
		bIsFlying = C->IsFlyingNow();
		bIsRiding = C->GetMode() == ECreatureMode::Ridden;
		bIsFainted = C->IsFainted();
		bInCombat = C->GetCombatTarget() != nullptr;
		if (const AActor* T = C->GetCombatTarget())
		{
			LookYaw = FMath::Clamp(FRotator::NormalizeAxis((T->GetActorLocation() - C->GetActorLocation()).Rotation().Yaw - Facing.Yaw), -70.f, 70.f);
		}
		else
		{
			LookYaw = FMath::FInterpTo(LookYaw, 0.f, Dt, 3.f);
		}
	}
	else if (const AAetherPlayerCharacter* P = Cast<AAetherPlayerCharacter>(Pawn))
	{
		WalkSpeed = 170.f;
		RunSpeed = 720.f;
		bIsSwimming = P->IsSwimming();
		bIsRiding = P->IsRiding();
		bIsAiming = P->IsAiming();
		bIsFainted = P->IsDowned();
	}

	// 0 -> 1 (marche) -> 2 (course)
	Gait = Speed <= WalkSpeed ? Speed / FMath::Max(1.f, WalkSpeed)
		: 1.f + (Speed - WalkSpeed) / FMath::Max(1.f, RunSpeed - WalkSpeed);
}
