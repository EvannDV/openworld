#include "AetherPlayerCharacter.h"

#include "AbilityEffects.h"
#include "AetherHUD.h"
#include "AetherSaveGame.h"
#include "AetherShrine.h"
#include "AetherWorldSubsystem.h"
#include "CaptureCapsule.h"
#include "Creature.h"
#include "CreatureCollectionComponent.h"
#include "CreatureDatabase.h"

#include "AIController.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimInstance.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "TimerManager.h"
#include "UObject/ConstructorHelpers.h"

static const TCHAR* GSaveSlot = TEXT("Aetherwild");

AAetherPlayerCharacter::AAetherPlayerCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	GetCapsuleComponent()->InitCapsuleSize(34.f, 88.f);

	bUseControllerRotationYaw = false;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;

	UCharacterMovementComponent* CMC = GetCharacterMovement();
	CMC->bOrientRotationToMovement = true;
	CMC->RotationRate = FRotator(0.f, 540.f, 0.f);
	CMC->MaxWalkSpeed = 380.f;
	CMC->JumpZVelocity = 520.f;
	CMC->AirControl = 0.35f;
	CMC->BrakingDecelerationWalking = 1800.f;
	CMC->BrakingDecelerationFlying = 1200.f;
	CMC->SetWalkableFloorAngle(50.f);
	CMC->MaxStepHeight = 50.f;

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = DefaultArmLength;
	CameraBoom->bUsePawnControlRotation = true;
	CameraBoom->SocketOffset = FVector(0.f, 55.f, 65.f);
	CameraBoom->bEnableCameraLag = true;
	CameraBoom->CameraLagSpeed = 14.f;

	FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
	FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	FollowCamera->bUsePawnControlRotation = false;
	FollowCamera->FieldOfView = 85.f;

	Collection = CreateDefaultSubobject<UCreatureCollectionComponent>(TEXT("Collection"));

	FallbackBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("FallbackBody"));
	FallbackBody->SetupAttachment(RootComponent);
	FallbackBody->SetMobility(EComponentMobility::Movable);
	FallbackBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	FallbackBody->SetRelativeScale3D(FVector(0.55f, 0.55f, 1.76f));
	FallbackBody->SetVisibility(false);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cyl(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (Cyl.Succeeded()) FallbackBody->SetStaticMesh(Cyl.Object);

	GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

void AAetherPlayerCharacter::BeginPlay()
{
	Super::BeginPlay();
	SetupVisuals();

	UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	if (!LoadProgress())
	{
		if (DB)
		{
			FVector Start = DB->PlayerStart;
			FHitResult Hit;
			FCollisionQueryParams P(SCENE_QUERY_STAT(PlayerStart), false, this);
			if (GetWorld()->LineTraceSingleByObjectType(Hit, Start + FVector(0, 0, 50000.f), Start - FVector(0, 0, 50000.f),
				FCollisionObjectQueryParams(ECC_WorldStatic), P))
			{
				Start = Hit.ImpactPoint;
			}
			SetActorLocation(Start + FVector(0, 0, 120.f), false, nullptr, ETeleportType::TeleportPhysics);
		}
		RespawnLocation = GetActorLocation();
		GiveStarterIfNeeded();
		Notify(TEXT("Bienvenue a Aetherwild ! Choisis ton premier compagnon : touches 1, 2 ou 3"), FLinearColor(1.f, 0.9f, 0.5f));
	}
	else
	{
		Notify(TEXT("Partie chargee. F1 : aide"), FLinearColor(0.7f, 0.9f, 1.f));
	}
}

void AAetherPlayerCharacter::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Reason == EEndPlayReason::Quit || Reason == EEndPlayReason::EndPlayInEditor)
	{
		if (!bNeedsStarter) SaveProgress();
	}
	Super::EndPlay(Reason);
}

void AAetherPlayerCharacter::SetupVisuals()
{
	UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	// Un Blueprint enfant (ex. BP_Tamer avec un MetaHuman) a deja son mesh et son AnimBP : on les garde tels quels.
	if (GetMesh()->GetSkeletalMeshAsset())
	{
		bUsesAnimBlueprint = GetMesh()->GetAnimClass() != nullptr;
		if (DB) Anims = DB->GetPlayerVisuals().Anims;
		for (auto It = Anims.CreateIterator(); It; ++It)
		{
			if (!It->Value || It->Value->GetSkeleton() != GetMesh()->GetSkeletalMeshAsset()->GetSkeleton()) It.RemoveCurrent();
		}
		return;
	}
	if (!DB) return;
	const FCreatureVisuals& V = DB->GetPlayerVisuals();
	if (V.Mesh)
	{
		Anims = V.Anims;
		for (auto It = Anims.CreateIterator(); It; ++It)
		{
			if (!It->Value || It->Value->GetSkeleton() != V.Mesh->GetSkeleton()) It.RemoveCurrent();
		}
		GetMesh()->SetSkeletalMeshAsset(V.Mesh);
		const FBoxSphereBounds B = V.Mesh->GetBounds();
		const float S = DB->PlayerHeightCm / FMath::Max(1.f, B.BoxExtent.Z * 2.f);
		const float HH = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
		GetMesh()->SetRelativeScale3D(FVector(S));
		GetMesh()->SetRelativeLocation(FVector(0.f, 0.f, -HH - (B.Origin.Z - B.BoxExtent.Z) * S));
		GetMesh()->SetRelativeRotation(FRotator(0.f, DB->PlayerMeshYaw, 0.f));
		if (V.AnimClass)
		{
			bUsesAnimBlueprint = true;
			GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
			GetMesh()->SetAnimInstanceClass(V.AnimClass);
		}
		else
		{
			GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
			PlayAnim(TEXT("Idle"), true);
		}
	}
	else
	{
		FallbackBody->SetVisibility(true);
		FallbackBody->SetRelativeLocation(FVector::ZeroVector);
	}
}

float AAetherPlayerCharacter::SeaLevel() const
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	return DB ? DB->SeaLevelZ : 0.f;
}

int32 AAetherPlayerCharacter::GetTamerLevel() const
{
	return Collection ? Collection->GetTamerLevel() : 1;
}

ACreature* AAetherPlayerCharacter::GetActiveCompanion() const
{
	return Collection ? Collection->GetActiveCompanion() : nullptr;
}

// ---------------------------------------------------------------------------------------------
// Tick
// ---------------------------------------------------------------------------------------------

void AAetherPlayerCharacter::Tick(float Dt)
{
	Super::Tick(Dt);
	if (bDowned) return;

	if (!IsRiding())
	{
		UpdateWater(Dt);
	}
	UpdateHover(Dt);

	RegenDelay -= Dt;
	if (RegenDelay <= 0.f && HP < MaxHP) HP = FMath::Min(MaxHP, HP + 4.f * Dt);

	const float TargetArm = bAiming ? 210.f : DefaultArmLength;
	CameraBoom->TargetArmLength = FMath::FInterpTo(CameraBoom->TargetArmLength, TargetArm, Dt, 10.f);
	FollowCamera->FieldOfView = FMath::FInterpTo(FollowCamera->FieldOfView, bAiming ? 68.f : 85.f, Dt, 10.f);

	if (ACreature* L = LockedTarget.Get())
	{
		if (L->IsFainted() || L->IsHidden() || FVector::Dist(L->GetActorLocation(), GetActorLocation()) > 5000.f) LockedTarget = nullptr;
	}

	AutoSaveTimer += Dt;
	if (AutoSaveTimer > 180.f && !bNeedsStarter)
	{
		AutoSaveTimer = 0.f;
		SaveProgress();
	}
	UpdateAnimation();
}

void AAetherPlayerCharacter::UpdateWater(float Dt)
{
	UCharacterMovementComponent* CMC = GetCharacterMovement();
	const float Sea = SeaLevel();
	const float HH = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const FVector L = GetActorLocation();
	const float Bottom = L.Z - HH;

	if (!bSwimming && Bottom < Sea - HH * 0.8f)
	{
		bSwimming = true;
		CMC->SetMovementMode(MOVE_Flying);
	}
	if (!bSwimming) return;

	FVector V = CMC->Velocity;
	V.Z = FMath::Clamp(((Sea - HH * 0.55f) - L.Z) * 3.f, -300.f, 300.f);
	CMC->Velocity = V;
	CMC->MaxFlySpeed = bSprinting ? 460.f : 300.f;

	FHitResult Hit;
	FCollisionQueryParams P(SCENE_QUERY_STAT(PlayerSwim), false, this);
	if (GetWorld()->LineTraceSingleByObjectType(Hit, L, L - FVector(0, 0, HH + 30.f), FCollisionObjectQueryParams(ECC_WorldStatic), P)
		&& Hit.ImpactPoint.Z > Sea - HH * 0.9f)
	{
		bSwimming = false;
		CMC->SetMovementMode(MOVE_Walking);
	}
}

void AAetherPlayerCharacter::UpdateHover(float Dt)
{
	HoverTimer -= Dt;
	if (HoverTimer > 0.f) return;
	HoverTimer = 0.08f;
	HoveredCreature = nullptr;
	APlayerController* PC = Cast<APlayerController>(IsRiding() ? GetMount()->GetController() : GetController());
	if (!PC || !PC->PlayerCameraManager) return;
	const FVector Start = PC->PlayerCameraManager->GetCameraLocation();
	const FVector Dir = PC->PlayerCameraManager->GetCameraRotation().Vector();
	TArray<FHitResult> Hits;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(AetherHover), false, this);
	if (ACreature* M = GetMount()) Params.AddIgnoredActor(M);
	GetWorld()->SweepMultiByObjectType(Hits, Start, Start + Dir * 6000.f, FQuat::Identity, FCollisionObjectQueryParams(ECC_Pawn),
		FCollisionShape::MakeSphere(70.f), Params);
	for (const FHitResult& H : Hits)
	{
		ACreature* C = Cast<ACreature>(H.GetActor());
		if (C && C->IsWild() && !C->IsFainted() && !C->IsHidden())
		{
			HoveredCreature = C;
			return;
		}
	}
}

// ---------------------------------------------------------------------------------------------
// Animation
// ---------------------------------------------------------------------------------------------

void AAetherPlayerCharacter::PlayAnim(FName Key, bool bLoop, float Rate)
{
	if (bUsesAnimBlueprint) return;
	UAnimSequence* Seq = Anims.FindRef(Key);
	if (!Seq) { Key = TEXT("Idle"); Seq = Anims.FindRef(Key); }
	if (!Seq) return;
	if (CurrentAnim != Key || !bLoop)
	{
		GetMesh()->PlayAnimation(Seq, bLoop);
		CurrentAnim = bLoop ? Key : NAME_None;
	}
	GetMesh()->SetPlayRate(Rate);
}

void AAetherPlayerCharacter::UpdateAnimation()
{
	if (bUsesAnimBlueprint || Anims.Num() == 0) return;
	const float Now = GetWorld()->GetTimeSeconds();
	if (IsRiding()) { PlayAnim(TEXT("Ride"), true); return; }
	if (Now < ThrowAnimEnd) return;
	const float Speed = GetVelocity().Size2D();
	if (bSwimming) PlayAnim(TEXT("Swim"), true, FMath::Clamp(Speed / 250.f, 0.5f, 1.6f));
	else if (Speed > 470.f) PlayAnim(TEXT("Run"), true, FMath::Clamp(Speed / 520.f, 0.7f, 1.6f));
	else if (Speed > 15.f) PlayAnim(TEXT("Walk"), true, FMath::Clamp(Speed / 170.f, 0.6f, 2.4f));
	else PlayAnim(TEXT("Idle"), true);
}

// ---------------------------------------------------------------------------------------------
// Commandes
// ---------------------------------------------------------------------------------------------

void AAetherPlayerCharacter::Move(const FVector2D& Input)
{
	if (bDowned || !Controller) return;
	const FRotator Yaw(0.f, Controller->GetControlRotation().Yaw, 0.f);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), Input.Y);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), Input.X);
}

void AAetherPlayerCharacter::Look(const FVector2D& Input)
{
	AddControllerYawInput(Input.X);
	AddControllerPitchInput(-Input.Y);
}

void AAetherPlayerCharacter::SetSprint(bool bOn)
{
	bSprinting = bOn;
	if (bOn) bSneaking = false;
	GetCharacterMovement()->MaxWalkSpeed = bSprinting ? 720.f : (bSneaking ? 170.f : 380.f);
}

void AAetherPlayerCharacter::ToggleSneak()
{
	bSneaking = !bSneaking;
	SetSprint(false);
	Notify(bSneaking ? TEXT("Discretion : les creatures craintives te remarquent moins") : TEXT("Discretion desactivee"), FLinearColor(0.7f, 0.7f, 0.9f));
}

void AAetherPlayerCharacter::SetAiming(bool bOn)
{
	bAiming = bOn && !IsRiding();
	bUseControllerRotationYaw = bAiming;
	GetCharacterMovement()->bOrientRotationToMovement = !bAiming;
}

FVector AAetherPlayerCharacter::GetAimPoint() const
{
	const APlayerController* PC = Cast<APlayerController>(IsRiding() ? GetMount()->GetController() : GetController());
	if (!PC || !PC->PlayerCameraManager) return GetActorLocation() + GetActorForwardVector() * 1000.f;
	const FVector Start = PC->PlayerCameraManager->GetCameraLocation();
	const FVector End = Start + PC->PlayerCameraManager->GetCameraRotation().Vector() * 8000.f;
	FHitResult Hit;
	FCollisionQueryParams P(SCENE_QUERY_STAT(AetherAim), false, this);
	if (ACreature* C = GetActiveCompanion()) P.AddIgnoredActor(C);
	return GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, P) ? Hit.ImpactPoint : End;
}

AActor* AAetherPlayerCharacter::GetAimTarget() const
{
	if (ACreature* L = LockedTarget.Get()) return L;
	return HoveredCreature.Get();
}

void AAetherPlayerCharacter::PrimaryAction()
{
	if (bDowned || bNeedsStarter) return;
	if (IsRiding())
	{
		CommandAbility(1);
		return;
	}
	ACreature* Comp = GetActiveCompanion();
	if (bAiming || !Comp)
	{
		ThrowCapsule();
		return;
	}
	if (AActor* T = GetAimTarget())
	{
		Comp->SetCombatTarget(T);
		Notify(FString::Printf(TEXT("%s, attaque !"), *Comp->GetDisplayName()), FLinearColor(1.f, 0.8f, 0.5f));
	}
	else
	{
		Notify(TEXT("Vise une creature (ou maintiens le clic droit pour lancer une capsule)"), FLinearColor::Gray);
	}
}

void AAetherPlayerCharacter::ThrowCapsule()
{
	const float Now = GetWorld()->GetTimeSeconds();
	if (Now - LastThrowTime < 0.8f) return;
	const ECapsuleTier Tier = Collection->SelectedCapsule;
	if (!Collection->ConsumeCapsule(Tier))
	{
		Notify(FString::Printf(TEXT("Plus de %s ! (T pour changer)"), *Aether::CapsuleName(Tier)), FLinearColor(1.f, 0.5f, 0.4f));
		return;
	}
	LastThrowTime = Now;
	FVector Start = GetActorLocation() + GetActorForwardVector() * 50.f + FVector(0, 0, 60.f);
	if (GetMesh()->DoesSocketExist(TEXT("hand_socket_r"))) Start = GetMesh()->GetSocketLocation(TEXT("hand_socket_r"));
	const FVector Target = GetAimPoint();
	const FVector Dir = (Target - Start).GetSafeNormal();
	const float Dist = FVector::Dist(Target, Start);
	const FVector Vel = Dir * FMath::Clamp(Dist * 1.3f, 1400.f, 2600.f) + FVector(0, 0, FMath::Clamp(Dist * 0.12f, 120.f, 420.f));

	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	SP.Instigator = this;
	if (ACaptureCapsule* Caps = GetWorld()->SpawnActor<ACaptureCapsule>(ACaptureCapsule::StaticClass(), Start, Dir.Rotation(), SP))
	{
		Caps->Throw(this, Tier, Vel);
	}
	if (UAnimSequence* Throw = Anims.FindRef(TEXT("Throw")))
	{
		if (bUsesAnimBlueprint)
		{
			if (UAnimInstance* AI = GetMesh()->GetAnimInstance()) AI->PlaySlotAnimationAsDynamicMontage(Throw, TEXT("DefaultSlot"), 0.1f, 0.2f);
		}
		else
		{
			GetMesh()->PlayAnimation(Throw, false);
			CurrentAnim = NAME_None;
		}
		ThrowAnimEnd = Now + Throw->GetPlayLength();
	}
	if (!bAiming) SetActorRotation(FRotator(0.f, Dir.Rotation().Yaw, 0.f));
}

void AAetherPlayerCharacter::CommandAbility(int32 Slot)
{
	if (bDowned || bNeedsStarter) return;
	ACreature* C = IsRiding() ? GetMount() : GetActiveCompanion();
	if (!C)
	{
		Notify(TEXT("Aucun compagnon dehors (G pour le faire sortir)"), FLinearColor::Gray);
		return;
	}
	const TArray<FName>& Abilities = C->GetData().Abilities;
	if (!Abilities.IsValidIndex(Slot - 1)) return;
	const FName Id = Abilities[Slot - 1];
	AActor* T = GetAimTarget();
	if (IsRiding())
	{
		C->TryUseAbility(Id, T);
		return;
	}
	if (!T) T = C->GetCombatTarget();
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	const FAbilityDef* A = DB ? DB->FindAbility(Id) : nullptr;
	if (A && (A->Shape == EAbilityShape::Buff || A->Shape == EAbilityShape::Heal))
	{
		C->TryUseAbility(Id, T);
		return;
	}
	if (!T)
	{
		Notify(TEXT("Vise une creature sauvage"), FLinearColor::Gray);
		return;
	}
	C->SetCombatTarget(T, Id);
}

void AAetherPlayerCharacter::CommandUltimate()
{
	ACreature* C = IsRiding() ? GetMount() : GetActiveCompanion();
	if (!C || C->GetSpecies().Ultimate.IsNone()) return;
	if (C->Resonance < 100.f)
	{
		Notify(FString::Printf(TEXT("Resonance insuffisante (%d%%)"), FMath::RoundToInt(C->Resonance)), FLinearColor::Gray);
		return;
	}
	AActor* T = GetAimTarget();
	if (!T) T = C->GetCombatTarget();
	if (IsRiding()) C->TryUseAbility(C->GetSpecies().Ultimate, T);
	else if (T) C->SetCombatTarget(T, C->GetSpecies().Ultimate);
}

void AAetherPlayerCharacter::ToggleCompanion()
{
	if (bDowned || bNeedsStarter) return;
	if (IsRiding()) Dismount();
	Collection->ToggleDeploy();
}

void AAetherPlayerCharacter::CycleParty(int32 Direction)
{
	Collection->SelectNext(Direction);
}

void AAetherPlayerCharacter::CycleCapsule()
{
	Collection->CycleCapsule();
	Notify(FString::Printf(TEXT("%s (x%d)"), *Aether::CapsuleName(Collection->SelectedCapsule), Collection->GetCapsuleCount(Collection->SelectedCapsule)),
		Aether::CapsuleColor(Collection->SelectedCapsule));
}

void AAetherPlayerCharacter::CycleTarget()
{
	TArray<ACreature*> Candidates;
	const FVector Fwd = GetControlRotation().Vector().GetSafeNormal2D();
	for (TActorIterator<ACreature> It(GetWorld()); It; ++It)
	{
		ACreature* C = *It;
		const FVector To = C->GetActorLocation() - GetActorLocation();
		if (C->IsWild() && !C->IsFainted() && !C->IsHidden() && To.Size() < 3500.f && FVector::DotProduct(To.GetSafeNormal2D(), Fwd) > 0.2f)
		{
			Candidates.Add(C);
		}
	}
	if (Candidates.Num() == 0) { LockedTarget = nullptr; return; }
	Candidates.Sort([this](const ACreature& A, const ACreature& B)
	{
		return FVector::DistSquared(A.GetActorLocation(), GetActorLocation()) < FVector::DistSquared(B.GetActorLocation(), GetActorLocation());
	});
	const int32 Cur = Candidates.IndexOfByKey(LockedTarget.Get());
	LockedTarget = Candidates[(Cur + 1) % Candidates.Num()];
}

void AAetherPlayerCharacter::ToggleMount()
{
	if (IsRiding())
	{
		Dismount();
		return;
	}
	ACreature* C = GetActiveCompanion();
	if (!C)
	{
		Notify(TEXT("Fais sortir une creature chevauchable (G)"), FLinearColor::Gray);
		return;
	}
	if (!C->GetSpecies().bRideable)
	{
		Notify(FString::Printf(TEXT("%s ne peut pas etre chevauche"), *C->GetDisplayName()), FLinearColor::Gray);
		return;
	}
	if (!C->CanBeRidden()) return;
	if (FVector::Dist(C->GetActorLocation(), GetActorLocation()) > C->GetBodyRadius() + 600.f)
	{
		Notify(TEXT("Approche-toi de ton compagnon"), FLinearColor::Gray);
		return;
	}
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC) return;

	SetAiming(false);
	C->StoredAIController = C->GetController();
	GetCharacterMovement()->StopMovementImmediately();
	GetCharacterMovement()->DisableMovement();
	SetActorEnableCollision(false);

	// selle : position du socket "saddle" exprimee dans le repere de la creature
	FVector Offset(0.f, 0.f, C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
	if (USkeletalMeshComponent* SM = C->GetVisualMesh())
	{
		if (SM->DoesSocketExist(C->GetSaddleSocket()))
		{
			Offset = C->GetActorTransform().InverseTransformPosition(SM->GetSocketLocation(C->GetSaddleSocket()));
		}
	}
	AttachToActor(C, FAttachmentTransformRules(EAttachmentRule::KeepRelative, EAttachmentRule::KeepRelative, EAttachmentRule::KeepWorld, false));
	SetActorRelativeLocation(Offset + FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() * 0.35f));
	SetActorRelativeRotation(FRotator::ZeroRotator);

	const FRotator ControlRot = PC->GetControlRotation();
	PC->Possess(C);
	PC->SetControlRotation(ControlRot);
	C->OnMounted(this);
	Mount = C;
	Notify(FString::Printf(TEXT("Tu chevauches %s  (E : descendre, Maj : galop%s)"), *C->GetDisplayName(),
		C->GetSpecies().CanFly() ? TEXT(", Espace : envol, Ctrl : descendre") : TEXT("")), FLinearColor(0.6f, 1.f, 0.8f));
}

void AAetherPlayerCharacter::Dismount()
{
	ACreature* C = Mount.Get();
	if (!C) return;
	APlayerController* PC = Cast<APlayerController>(C->GetController());
	const FRotator ControlRot = PC ? PC->GetControlRotation() : GetActorRotation();

	DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
	FVector Spot = C->GetActorLocation() + C->GetActorRightVector() * (C->GetBodyRadius() + 90.f);
	FHitResult Hit;
	FCollisionQueryParams P(SCENE_QUERY_STAT(Dismount), false, this);
	P.AddIgnoredActor(C);
	if (GetWorld()->LineTraceSingleByObjectType(Hit, Spot + FVector(0, 0, 3000.f), Spot - FVector(0, 0, 30000.f), FCollisionObjectQueryParams(ECC_WorldStatic), P))
	{
		Spot = Hit.ImpactPoint;
	}
	Spot.Z = FMath::Max(Spot.Z, SeaLevel() - 60.f);
	SetActorLocation(Spot + FVector(0, 0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 10.f), false, nullptr, ETeleportType::TeleportPhysics);
	SetActorRotation(FRotator(0.f, ControlRot.Yaw, 0.f));
	SetActorEnableCollision(true);
	GetCharacterMovement()->SetMovementMode(MOVE_Falling);

	Mount = nullptr;
	if (PC)
	{
		PC->Possess(this);
		PC->SetControlRotation(ControlRot);
	}
	if (AController* AIC = C->StoredAIController.Get()) AIC->Possess(C);
	else C->SpawnDefaultController();
	C->OnDismounted();
}

void AAetherPlayerCharacter::Interact()
{
	if (bDowned) return;
	if (IsNearShrine())
	{
		Collection->HealAll();
		HP = MaxHP;
		RespawnLocation = GetActorLocation();
		SaveProgress();
		Collection->AddCapsules(ECapsuleTier::Micro, FMath::Max(0, 5 - Collection->GetCapsuleCount(ECapsuleTier::Micro)));
		Notify(TEXT("Sanctuaire : equipe soignee, capsules rechargees, partie sauvegardee. (B : Sanctuaire de stockage)"), FLinearColor(0.5f, 1.f, 1.f));
		AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), FLinearColor(0.5f, 1.f, 1.f), 400.f, 1.f);
	}
}

bool AAetherPlayerCharacter::IsNearShrine() const
{
	for (TActorIterator<AAetherShrine> It(GetWorld()); It; ++It)
	{
		if (FVector::Dist(It->GetActorLocation(), GetActorLocation()) < 700.f) return true;
	}
	return false;
}

void AAetherPlayerCharacter::UsePotion()
{
	if (Collection->UsePotion()) Notify(FString::Printf(TEXT("Potion utilisee (reste %d)"), Collection->Potions), FLinearColor(0.4f, 1.f, 0.5f));
	else Notify(TEXT("Pas de potion utilisable"), FLinearColor::Gray);
}

float AAetherPlayerCharacter::GetCaptureChancePreview(FString& OutReason) const
{
	const ACreature* C = Cast<ACreature>(GetAimTarget());
	if (!C) return -1.f;
	return ACaptureCapsule::ComputeCaptureChance(C, Collection->SelectedCapsule, GetTamerLevel(), OutReason);
}

// ---------------------------------------------------------------------------------------------
// Evenements
// ---------------------------------------------------------------------------------------------

void AAetherPlayerCharacter::ReceiveCreatureDamage(float Damage, ACreature* From)
{
	if (bDowned || IsRiding()) return;
	HP = FMath::Max(0.f, HP - Damage);
	RegenDelay = 6.f;
	AAetherHUD::PushFloatingText(GetWorld(), GetActorLocation() + FVector(0, 0, 110.f), FString::Printf(TEXT("-%d"), FMath::RoundToInt(Damage)), FLinearColor(1.f, 0.3f, 0.3f));
	if (ACreature* C = GetActiveCompanion())
	{
		if (From && !C->GetCombatTarget()) C->SetCombatTarget(From);
	}
	if (HP <= 0.f)
	{
		bDowned = true;
		Notify(TEXT("Tu t'evanouis... Retour au dernier sanctuaire."), FLinearColor(1.f, 0.3f, 0.3f));
		Collection->Recall(true);
		GetCharacterMovement()->DisableMovement();
		FTimerHandle H;
		GetWorldTimerManager().SetTimer(H, this, &AAetherPlayerCharacter::Respawn, 3.f, false);
	}
}

void AAetherPlayerCharacter::Respawn()
{
	bDowned = false;
	HP = MaxHP;
	Collection->HealAll();
	Collection->Coins = FMath::RoundToInt(Collection->Coins * 0.9f);
	SetActorLocation(RespawnLocation + FVector(0, 0, 100.f), false, nullptr, ETeleportType::TeleportPhysics);
	GetCharacterMovement()->SetMovementMode(MOVE_Walking);
}

void AAetherPlayerCharacter::OnWildDefeated(ACreature* Wild, int32 XP)
{
	if (!Wild) return;
	Collection->Seen.Add(Wild->GetSpecies().Id);
	Collection->AddTamerXP(FMath::Max(1, XP / 3));
	const int32 Coins = 4 + Wild->GetData().Level * 2;
	Collection->Coins += Coins;
	FString Loot;
	if (FMath::FRand() < 0.22f) { Collection->AddCapsules(ECapsuleTier::Micro, 1); Loot += TEXT(", +1 micro-capsule"); }
	if (FMath::FRand() < 0.10f) { ++Collection->Potions; Loot += TEXT(", +1 potion"); }
	if (FMath::FRand() < 0.04f) { Collection->AddCapsules(ECapsuleTier::Ultra, 1); Loot += TEXT(", +1 ultra-capsule"); }
	Notify(FString::Printf(TEXT("%s sauvage est K.O. ! +%d XP, +%d pieces%s"), *Wild->GetDisplayName(), XP, Coins, *Loot), FLinearColor(0.9f, 0.9f, 0.6f));
}

void AAetherPlayerCharacter::OnCompanionFainted(ACreature* Companion)
{
	if (!Companion) return;
	Notify(FString::Printf(TEXT("%s est K.O. !"), *Companion->GetDisplayName()), FLinearColor(1.f, 0.35f, 0.35f));
	FTimerHandle H;
	TWeakObjectPtr<UCreatureCollectionComponent> WeakColl(Collection);
	GetWorldTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [WeakColl]()
	{
		if (UCreatureCollectionComponent* C = WeakColl.Get()) C->Recall();
	}), 1.5f, false);
}

void AAetherPlayerCharacter::OnCaptureStarted(ACreature* Target, float Chance)
{
	LastCaptureChance = Chance;
	if (Target) Notify(FString::Printf(TEXT("Capture de %s... (%d%%)"), *Target->GetDisplayName(), FMath::RoundToInt(Chance * 100.f)), FLinearColor(0.6f, 0.9f, 1.f));
}

void AAetherPlayerCharacter::OnCaptureSuccess(ACreature* Target, ECapsuleTier Tier)
{
	if (!Target) return;
	FCreatureInstance Inst = Target->GetData();
	if (!Inst.Guid.IsValid()) Inst.Guid = FGuid::NewGuid();
	const bool bNewSpecies = !Collection->Caught.Contains(Inst.SpeciesId);
	bool bToBox = false;
	Collection->AddCreature(Inst, bToBox);
	const FSpeciesDef& S = Target->GetSpecies();
	Collection->AddTamerXP(S.BaseXP * Inst.Level / 4 + (int32)S.Rarity * 25);
	Notify(FString::Printf(TEXT("%s (%s, niv. %d) capture%s ! -> %s"), *Target->GetDisplayName(), *Aether::RarityName(S.Rarity), Inst.Level,
		Inst.bPrismatic ? TEXT(" - PRISMATIQUE") : TEXT(""), bToBox ? TEXT("Sanctuaire (poche pleine)") : TEXT("poche")), Aether::RarityColor(S.Rarity));
	if (bNewSpecies) Notify(TEXT("Nouvelle espece enregistree dans le Bestiaire !"), FLinearColor(1.f, 0.9f, 0.4f));
	SaveProgress();
}

void AAetherPlayerCharacter::OnCaptureFailed(ACreature* Target)
{
	if (Target) Notify(FString::Printf(TEXT("%s s'est libere !"), *Target->GetDisplayName()), FLinearColor(1.f, 0.5f, 0.3f));
}

void AAetherPlayerCharacter::RequestEvolution(ACreature* Companion)
{
	if (!Companion) return;
	const FSpeciesDef& S = Companion->GetSpecies();
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	const FSpeciesDef* Next = DB ? DB->FindSpecies(S.EvolvesTo) : nullptr;
	if (!Next) return;
	Notify(FString::Printf(TEXT("%s se metamorphose en %s !"), *Companion->GetDisplayName(), *Next->DisplayName), Aether::RarityColor(Next->Rarity));
	AAetherVfx::SpawnBurst(GetWorld(), Companion->GetActorLocation(), FLinearColor(1.f, 1.f, 1.f), Companion->GetBodyRadius() * 4.f + 200.f, 1.5f);
	const FGuid Guid = Companion->GetData().Guid;
	const FName NewId = S.EvolvesTo;
	FTimerHandle H;
	TWeakObjectPtr<UCreatureCollectionComponent> WeakColl(Collection);
	GetWorldTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [WeakColl, Guid, NewId]()
	{
		if (UCreatureCollectionComponent* C = WeakColl.Get()) C->Evolve(Guid, NewId);
	}), 1.2f, false);
}

void AAetherPlayerCharacter::Notify(const FString& Message, const FLinearColor& Color)
{
	AAetherHUD::PushMessage(GetWorld(), Message, Color);
	UE_LOG(LogAether, Log, TEXT("%s"), *Message);
}

// ---------------------------------------------------------------------------------------------
// Starter + sauvegarde
// ---------------------------------------------------------------------------------------------

void AAetherPlayerCharacter::GiveStarterIfNeeded()
{
	bNeedsStarter = Collection->Party.Num() == 0;
}

void AAetherPlayerCharacter::ChooseStarter(int32 Index)
{
	if (!bNeedsStarter) return;
	UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	if (!DB || !DB->StarterSpecies.IsValidIndex(Index)) return;
	FRandomStream Rng(FMath::Rand());
	FCreatureInstance Inst = DB->MakeInstance(DB->StarterSpecies[Index], 5, Rng);
	bool bToBox = false;
	Collection->AddCreature(Inst, bToBox);
	bNeedsStarter = false;
	Collection->Deploy(0);
	Notify(TEXT("Clic droit : viser / Clic gauche : lancer une capsule ou ordonner une attaque. F1 : toutes les commandes."), FLinearColor(1.f, 0.9f, 0.5f));
	SaveProgress();
}

void AAetherPlayerCharacter::SaveProgress()
{
	UAetherSaveGame* Save = Cast<UAetherSaveGame>(UGameplayStatics::CreateSaveGameObject(UAetherSaveGame::StaticClass()));
	if (!Save) return;
	if (ACreature* C = GetActiveCompanion()) Collection->SyncFromCompanion(C->GetData());
	Save->Party = Collection->Party;
	Save->Box = Collection->Box;
	Save->Capsules = Collection->Capsules;
	Save->Potions = Collection->Potions;
	Save->Coins = Collection->Coins;
	Save->TamerXP = Collection->TamerXP;
	Save->Seen = Collection->Seen.Array();
	Save->Caught = Collection->Caught.Array();
	Save->PlayerLocation = IsRiding() ? GetMount()->GetActorLocation() : GetActorLocation();
	Save->RespawnLocation = RespawnLocation;
	if (const UAetherWorldSubsystem* WS = UAetherWorldSubsystem::Get(this))
	{
		Save->TimeOfDay = WS->TimeOfDay;
		Save->Weather = WS->Weather;
	}
	UGameplayStatics::SaveGameToSlot(Save, GSaveSlot, 0);
}

bool AAetherPlayerCharacter::LoadProgress()
{
	if (!UGameplayStatics::DoesSaveGameExist(GSaveSlot, 0)) return false;
	const UAetherSaveGame* Save = Cast<UAetherSaveGame>(UGameplayStatics::LoadGameFromSlot(GSaveSlot, 0));
	if (!Save || Save->Party.Num() == 0) return false;
	Collection->Party = Save->Party;
	Collection->Box = Save->Box;
	Collection->Capsules = Save->Capsules;
	if (Collection->Capsules.Num() < 3) Collection->Capsules.SetNumZeroed(3);
	Collection->Potions = Save->Potions;
	Collection->Coins = Save->Coins;
	Collection->TamerXP = Save->TamerXP;
	Collection->Seen = TSet<FName>(Save->Seen);
	Collection->Caught = TSet<FName>(Save->Caught);
	RespawnLocation = Save->RespawnLocation;
	SetActorLocation(Save->PlayerLocation + FVector(0, 0, 150.f), false, nullptr, ETeleportType::TeleportPhysics);
	if (UAetherWorldSubsystem* WS = UAetherWorldSubsystem::Get(this))
	{
		WS->TimeOfDay = Save->TimeOfDay;
		WS->SetWeather(Save->Weather, true);
	}
	bNeedsStarter = false;
	return true;
}
