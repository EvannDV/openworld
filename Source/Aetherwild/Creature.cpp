#include "Creature.h"

#include "AbilityEffects.h"
#include "AetherHUD.h"
#include "AetherPlayerCharacter.h"
#include "AetherWorldSubsystem.h"
#include "CreatureCollectionComponent.h"
#include "CreatureDatabase.h"
#include "CreatureSpawner.h"

#include "AIController.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimInstance.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	UMaterialInterface* GBasicShapeMaterial = nullptr;
}

ACreature::ACreature()
{
	PrimaryActorTick.bCanEverTick = true;
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
	AIControllerClass = AAIController::StaticClass();

	bUseControllerRotationYaw = false;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;

	UCharacterMovementComponent* CMC = GetCharacterMovement();
	CMC->bOrientRotationToMovement = true;
	CMC->RotationRate = FRotator(0.f, 360.f, 0.f);
	CMC->MaxStepHeight = 60.f;
	CMC->SetWalkableFloorAngle(52.f);
	CMC->BrakingDecelerationFlying = 900.f;
	CMC->BrakingDecelerationWalking = 1200.f;
	CMC->JumpZVelocity = 650.f;

	GetCapsuleComponent()->InitCapsuleSize(40.f, 50.f);
	GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
	GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	FallbackBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("FallbackBody"));
	FallbackBody->SetupAttachment(GetCapsuleComponent());
	FallbackBody->SetMobility(EComponentMobility::Movable);
	FallbackBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	FallbackBody->SetVisibility(false);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (SphereMesh.Succeeded()) FallbackBody->SetStaticMesh(SphereMesh.Object);
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> BasicMat(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (BasicMat.Succeeded()) GBasicShapeMaterial = BasicMat.Object;

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(GetCapsuleComponent());
	CameraBoom->TargetArmLength = 650.f;
	CameraBoom->bUsePawnControlRotation = true;
	CameraBoom->bEnableCameraLag = true;
	CameraBoom->CameraLagSpeed = 9.f;
	CameraBoom->SocketOffset = FVector(0.f, 0.f, 160.f);
	CameraBoom->ProbeSize = 18.f;

	RideCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("RideCamera"));
	RideCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	RideCamera->bUsePawnControlRotation = false;
	RideCamera->FieldOfView = 80.f;

	Glow = CreateDefaultSubobject<UPointLightComponent>(TEXT("Glow"));
	Glow->SetupAttachment(GetCapsuleComponent());
	Glow->SetIntensityUnits(ELightUnits::Candelas);
	Glow->SetIntensity(40.f);
	Glow->SetAttenuationRadius(900.f);
	Glow->SetCastShadows(false);
	Glow->SetVisibility(false);
}

void ACreature::BeginPlay()
{
	Super::BeginPlay();
	if (HomeLocation.IsZero()) HomeLocation = GetActorLocation();
	BrainTimer = FMath::FRandRange(0.5f, 3.f);
}

float ACreature::Now() const
{
	return GetWorld() ? GetWorld()->GetTimeSeconds() : 0.f;
}

AAetherPlayerCharacter* ACreature::GetTamer() const { return Tamer.Get(); }
AAetherPlayerCharacter* ACreature::GetRider() const { return Rider.Get(); }

USkeletalMeshComponent* ACreature::GetVisualMesh() const { return GetMesh(); }

FString ACreature::GetDisplayName() const
{
	return Aether::DisplayNameOf(Data, &Species);
}

float ACreature::GetBodyRadius() const
{
	return GetCapsuleComponent()->GetScaledCapsuleRadius();
}

float ACreature::SeaLevel() const
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	return DB ? DB->SeaLevelZ : 0.f;
}

// ---------------------------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------------------------

void ACreature::InitCreature(const FCreatureInstance& InData, ECreatureMode InMode, AAetherPlayerCharacter* InTamer)
{
	UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	Data = InData;
	Mode = InMode;
	Tamer = InTamer;
	if (DB)
	{
		if (const FSpeciesDef* S = DB->FindSpecies(Data.SpeciesId)) Species = *S;
		else UE_LOG(LogAether, Error, TEXT("Espece inconnue : %s"), *Data.SpeciesId.ToString());
	}
	Stats = Aether::ComputeStats(Species, Data);
	if (Data.CurrentHP < 0.f || Data.CurrentHP > Stats.MaxHP) Data.CurrentHP = Stats.MaxHP;

	SetupVisuals();
	SetupMovement();
	HomeLocation = GetActorLocation();
	Brain = (Mode == ECreatureMode::Wild) ? ECreatureBrain::Idle : ECreatureBrain::Follow;
	HoverHeight = FMath::FRandRange(350.f, 900.f) * FMath::Clamp(Species.SizeMeters, 0.6f, 2.f);
}

void ACreature::SetupVisuals()
{
	UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	const float LevelScale = FMath::Clamp(0.9f + Data.Level * 0.004f, 0.9f, 1.15f);
	const float TargetSize = FMath::Max(20.f, Species.SizeMeters * 100.f * LevelScale);

	// Priorite : mesh deja defini dans un Blueprint enfant (artiste) > visual.mesh du JSON > modele procedural.
	USkeletalMesh* SkMesh = GetMesh()->GetSkeletalMeshAsset();
	const bool bFromBlueprint = SkMesh != nullptr;
	TSubclassOf<UAnimInstance> AnimClass = GetMesh()->GetAnimClass();
	if (DB)
	{
		const FCreatureVisuals& V = DB->GetVisuals(Species.Id);
		if (!SkMesh) SkMesh = V.Mesh;
		if (!AnimClass) AnimClass = V.AnimClass;
		Anims = V.Anims;
	}

	if (SkMesh)
	{
		if (!bFromBlueprint) GetMesh()->SetSkeletalMeshAsset(SkMesh);
		// on ne garde que les animations compatibles avec le squelette du modele
		for (auto It = Anims.CreateIterator(); It; ++It)
		{
			if (!It->Value || It->Value->GetSkeleton() != SkMesh->GetSkeleton()) It.RemoveCurrent();
		}
		const FBoxSphereBounds B = SkMesh->GetBounds();
		const float MaxDim = 2.f * FMath::Max3(B.BoxExtent.X, B.BoxExtent.Y, B.BoxExtent.Z);
		const bool bKeepScale = Species.bKeepMeshScale || bFromBlueprint;
		MeshBaseScale = bKeepScale ? GetMesh()->GetRelativeScale3D().X : TargetSize / FMath::Max(MaxDim, 1.f);
		const FVector Ext = B.BoxExtent * MeshBaseScale;
		const float Radius = FMath::Clamp(FMath::Min(Ext.X, Ext.Y) * 0.85f, 14.f, 220.f);
		HalfHeight = FMath::Clamp(FMath::Max(Radius, Ext.Z), 20.f, 400.f);
		GetCapsuleComponent()->SetCapsuleSize(Radius, HalfHeight);
		if (!bFromBlueprint)
		{
			const float BottomZ = (B.Origin.Z - B.BoxExtent.Z) * MeshBaseScale;
			GetMesh()->SetRelativeScale3D(FVector(MeshBaseScale));
			GetMesh()->SetRelativeLocation(FVector(0.f, 0.f, -HalfHeight - BottomZ));
			const float Yaw = Species.bOverrideYaw ? Species.MeshYaw : (DB ? DB->MeshYawOffset : -90.f);
			GetMesh()->SetRelativeRotation(FRotator(0.f, Yaw, 0.f));
		}
		if (AnimClass)
		{
			bUsesAnimBlueprint = true;
			GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
			GetMesh()->SetAnimInstanceClass(AnimClass);
		}
		else
		{
			GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
		}
		FallbackBody->SetVisibility(false);
		if (Data.bPrismatic)
		{
			if (UMaterialInstanceDynamic* MID = GetMesh()->CreateAndSetMaterialInstanceDynamic(0))
			{
				MID->SetVectorParameterValue(TEXT("Tint"), FLinearColor(1.5f, 1.2f, 0.45f));
			}
		}
		PlayAnim(TEXT("Idle"), true);
	}
	else
	{
		// Forme de secours si les assets n'ont pas encore ete importes.
		HalfHeight = FMath::Clamp(TargetSize * 0.3f, 20.f, 300.f);
		GetCapsuleComponent()->SetCapsuleSize(FMath::Min(HalfHeight, TargetSize * 0.3f), HalfHeight);
		FallbackBody->SetVisibility(true);
		FallbackBody->SetRelativeScale3D(FVector(TargetSize / 100.f, TargetSize / 160.f, HalfHeight * 2.f / 100.f));
		if (GBasicShapeMaterial)
		{
			FallbackMID = UMaterialInstanceDynamic::Create(GBasicShapeMaterial, this);
			FallbackMID->SetVectorParameterValue(TEXT("Color"), Species.PrimaryColor);
			FallbackBody->SetMaterial(0, FallbackMID);
		}
	}

	CameraBoom->TargetArmLength = FMath::Max(550.f, TargetSize * 2.4f);
	CameraBoom->SocketOffset = FVector(0.f, 0.f, HalfHeight + 90.f);
	Glow->SetLightColor(Species.AccentColor);
	Glow->SetAttenuationRadius(FMath::Max(700.f, TargetSize * 6.f));
	UpdateGlow();
}

void ACreature::SetupMovement()
{
	UCharacterMovementComponent* CMC = GetCharacterMovement();
	const float SpeedMul = 1.f + Stats.Speed * 0.004f;
	CMC->MaxWalkSpeed = Species.WalkSpeed * SpeedMul;
	CMC->MaxFlySpeed = Species.RunSpeed * SpeedMul;
	CMC->MaxSwimSpeed = Species.RunSpeed * SpeedMul;
	if (Species.CanFly() && Mode != ECreatureMode::Ridden)
	{
		CMC->SetMovementMode(MOVE_Flying);
	}
	else if (Species.IsAquaticOnly())
	{
		bSwimming = true;
		CMC->SetMovementMode(MOVE_Flying);
	}
	else
	{
		CMC->SetMovementMode(MOVE_Walking);
	}
}

// ---------------------------------------------------------------------------------------------
// Tick
// ---------------------------------------------------------------------------------------------

void ACreature::Tick(float Dt)
{
	Super::Tick(Dt);

	if (Brain == ECreatureBrain::Captured) return;
	if (Brain == ECreatureBrain::Fainted)
	{
		UpdateFaint(Dt);
		return;
	}

	UpdateStatus(Dt);
	if (AttackBuffEnd > 0.f && Now() > AttackBuffEnd)
	{
		AttackBuff = 1.f;
		AttackBuffEnd = 0.f;
	}

	switch (Mode)
	{
	case ECreatureMode::Wild:      UpdateWild(Dt); break;
	case ECreatureMode::Companion: UpdateCompanion(Dt); break;
	case ECreatureMode::Ridden:
	{
		UCharacterMovementComponent* CMC = GetCharacterMovement();
		const float Base = Species.RunSpeed * (1.f + Stats.Speed * 0.004f);
		CMC->MaxWalkSpeed = bRiderSprint ? Base * 1.15f : Base * 0.55f;
		CMC->MaxFlySpeed = bRiderSprint ? Base * 1.6f : Base;
		if (bRiderFlying && !bSwimming)
		{
			bool bHit = false;
			const float G = GroundHeightAt(GetActorLocation(), bHit);
			if (bHit && RiderVerticalInput < 0.f && GetActorLocation().Z - HalfHeight - G < 40.f)
			{
				bRiderFlying = false;
				CMC->SetMovementMode(MOVE_Walking);
			}
		}
		break;
	}
	}

	UpdateFlightHover(Dt);
	UpdateWater(Dt);
	UpdateAnimation(Dt);

	PerceptionTimer -= Dt;
	GlowTimer -= Dt;
	if (GlowTimer <= 0.f)
	{
		GlowTimer = 1.f;
		UpdateGlow();
	}
}

void ACreature::UpdateGlow()
{
	const UAetherWorldSubsystem* WS = UAetherWorldSubsystem::Get(this);
	const bool bDark = WS && WS->GetPhase() != EDayPhase::Day;
	Glow->SetVisibility(Species.bEmitsLight && bDark && !IsHidden());
}

void ACreature::UpdateStatus(float Dt)
{
	if (Status == EAetherStatus::None) return;
	StatusTimeLeft -= Dt;
	if (Status == EAetherStatus::Burn)
	{
		BurnTick -= Dt;
		if (BurnTick <= 0.f)
		{
			BurnTick = 1.f;
			ReceiveRawDamage(FMath::Max(1.f, Stats.MaxHP * 0.03f), LastAttacker.Get());
		}
	}
	if (StatusTimeLeft <= 0.f)
	{
		Status = EAetherStatus::None;
		GetCharacterMovement()->MaxWalkSpeed = Species.WalkSpeed * (1.f + Stats.Speed * 0.004f);
	}
}

bool ACreature::CanAct() const
{
	return !IsFainted() && Status != EAetherStatus::Stunned && Status != EAetherStatus::Frozen && Status != EAetherStatus::Asleep;
}

float ACreature::GroundHeightAt(const FVector& L, bool& bHit) const
{
	FHitResult Hit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(AetherGround), false, this);
	const FVector Start(L.X, L.Y, L.Z + 2000.f);
	const FVector End(L.X, L.Y, L.Z - 20000.f);
	bHit = GetWorld()->LineTraceSingleByObjectType(Hit, Start, End, FCollisionObjectQueryParams(ECC_WorldStatic), Params);
	return bHit ? Hit.ImpactPoint.Z : L.Z - 20000.f;
}

bool ACreature::IsLocationWater(const FVector& L) const
{
	bool bHit = false;
	const float G = GroundHeightAt(FVector(L.X, L.Y, FMath::Max(L.Z, SeaLevel()) + 5000.f), bHit);
	return !bHit || G < SeaLevel() - 20.f;
}

void ACreature::UpdateWater(float Dt)
{
	UCharacterMovementComponent* CMC = GetCharacterMovement();
	const bool bFlyingNow = CMC->MovementMode == MOVE_Flying && !bSwimming;
	if (bFlyingNow) return;

	const float Sea = SeaLevel();
	const FVector L = GetActorLocation();
	const float Bottom = L.Z - HalfHeight;

	if (!bSwimming && Bottom < Sea - HalfHeight * 0.9f)
	{
		bSwimming = true;
		CMC->SetMovementMode(MOVE_Flying);
	}
	if (!bSwimming) return;

	float TargetZ = Sea - HalfHeight * 0.35f;
	if (Species.IsAquaticOnly() && Mode == ECreatureMode::Wild) TargetZ = Sea - HalfHeight * 0.15f;
	FVector V = CMC->Velocity;
	V.Z = FMath::Clamp((TargetZ - L.Z) * 2.5f, -250.f, 250.f);
	CMC->Velocity = V;
	const float SpeedMul = 1.f + Stats.Speed * 0.004f;
	CMC->MaxFlySpeed = (Species.CanSwim() ? Species.RunSpeed : Species.WalkSpeed * 0.6f) * SpeedMul;

	GroundTraceTimer -= Dt;
	if (GroundTraceTimer <= 0.f)
	{
		GroundTraceTimer = 0.25f;
		bool bHit = false;
		CachedGroundZ = GroundHeightAt(L, bHit);
		if (bHit && CachedGroundZ > Sea - HalfHeight * 0.8f && !Species.IsAquaticOnly())
		{
			bSwimming = false;
			CMC->SetMovementMode(MOVE_Walking);
		}
	}
}

void ACreature::UpdateFlightHover(float Dt)
{
	if (!Species.CanFly() || Mode == ECreatureMode::Ridden) return;
	UCharacterMovementComponent* CMC = GetCharacterMovement();
	if (CMC->MovementMode != MOVE_Flying) CMC->SetMovementMode(MOVE_Flying);
	bSwimming = false;

	GroundTraceTimer -= Dt;
	if (GroundTraceTimer <= 0.f)
	{
		GroundTraceTimer = 0.3f;
		bool bHit = false;
		CachedGroundZ = FMath::Max(GroundHeightAt(GetActorLocation(), bHit), SeaLevel());
	}
	float TargetZ = CachedGroundZ + HoverHeight;
	if (const AActor* T = CombatTarget.Get())
	{
		TargetZ = T->GetActorLocation().Z + 180.f;
	}
	else if (Mode == ECreatureMode::Companion)
	{
		TargetZ = CachedGroundZ + 260.f;
	}
	FVector V = CMC->Velocity;
	V.Z = FMath::Clamp((TargetZ - GetActorLocation().Z) * 1.5f, -450.f, 450.f);
	CMC->Velocity = V;
}

void ACreature::Landed(const FHitResult& Hit)
{
	Super::Landed(Hit);
	if (Mode == ECreatureMode::Ridden) bRiderFlying = false;
}

// ---------------------------------------------------------------------------------------------
// Deplacement
// ---------------------------------------------------------------------------------------------

bool ACreature::MoveTowards(const FVector& Dest, float SpeedScale, float AcceptRadius)
{
	if (Status == EAetherStatus::Rooted || !CanAct()) return false;
	FVector Dir = Dest - GetActorLocation();
	const UCharacterMovementComponent* CMC = GetCharacterMovement();
	const bool b3D = CMC->MovementMode == MOVE_Flying && !bSwimming;
	if (!b3D) Dir.Z = 0.f;
	if (Dir.Size2D() <= AcceptRadius) return true;

	const float SpeedMul = 1.f + Stats.Speed * 0.004f;
	const float SoakMul = (Status == EAetherStatus::Soaked) ? 0.7f : 1.f;
	const float Target = (SpeedScale > 1.01f ? Species.RunSpeed : Species.WalkSpeed * SpeedScale) * SpeedMul * SoakMul;
	GetCharacterMovement()->MaxWalkSpeed = Target;
	if (b3D) GetCharacterMovement()->MaxFlySpeed = Target * 1.2f;
	AddMovementInput(Dir.GetSafeNormal2D(), 1.f);
	return false;
}

void ACreature::FaceTowards(const FVector& Point, float Dt)
{
	FVector D = Point - GetActorLocation();
	D.Z = 0.f;
	if (D.IsNearlyZero()) return;
	const FRotator Target = D.Rotation();
	SetActorRotation(FMath::RInterpTo(GetActorRotation(), FRotator(0.f, Target.Yaw, 0.f), Dt, 8.f));
}

bool ACreature::PickWanderDestination()
{
	for (int32 Try = 0; Try < 5; ++Try)
	{
		const FVector2D R = FMath::RandPointInCircle(Species.IsAquaticOnly() ? 2500.f : 1600.f);
		FVector P = HomeLocation + FVector(R.X, R.Y, 0.f);
		bool bHit = false;
		const float G = GroundHeightAt(FVector(P.X, P.Y, P.Z + 10000.f), bHit);
		const bool bWater = !bHit || G < SeaLevel() - 30.f;
		if (Species.IsAquaticOnly() != bWater && !(Species.CanSwim() && !Species.IsAquaticOnly()) && !Species.CanFly())
		{
			continue;
		}
		if (Species.IsAquaticOnly() && !bWater) continue;
		P.Z = bHit ? FMath::Max(G, SeaLevel()) : SeaLevel();
		WanderTarget = P;
		bHasWanderTarget = true;
		return true;
	}
	return false;
}

// ---------------------------------------------------------------------------------------------
// IA : sauvage
// ---------------------------------------------------------------------------------------------

void ACreature::UpdateWild(float Dt)
{
	AAetherPlayerCharacter* Player = Cast<AAetherPlayerCharacter>(UGameplayStatics::GetPlayerCharacter(this, 0));
	if (!Player)
	{
		// le joueur chevauche : on recupere le cavalier
		if (ACreature* Mount = Cast<ACreature>(UGameplayStatics::GetPlayerPawn(this, 0))) Player = Mount->GetRider();
	}
	const float DistPlayer = Player ? FVector::Dist(Player->GetActorLocation(), GetActorLocation()) : 1e9f;

	if (PerceptionTimer <= 0.f)
	{
		PerceptionTimer = 0.35f;
		if (Player && Brain != ECreatureBrain::Fight && !Player->IsDowned())
		{
			ACreature* Comp = Player->GetActiveCompanion();
			AActor* Threat = (Comp && !Comp->IsFainted() && FVector::Dist(Comp->GetActorLocation(), GetActorLocation()) < DistPlayer)
				? static_cast<AActor*>(Comp) : static_cast<AActor*>(Player);
			if (Player->IsRiding()) Threat = Player->GetMount();
			switch (Species.Temperament)
			{
			case ETemperament::Aggressive:
				if (DistPlayer < 1800.f) SetCombatTarget(Threat);
				break;
			case ETemperament::Territorial:
				if (DistPlayer < 750.f) SetCombatTarget(Threat);
				break;
			case ETemperament::Skittish:
				if (DistPlayer < (Player->IsSneaking() ? 450.f : 1000.f) && Brain != ECreatureBrain::Flee)
				{
					Brain = ECreatureBrain::Flee;
					BrainTimer = 5.f;
				}
				break;
			default: break;
			}
		}
		if (Brain == ECreatureBrain::Fight)
		{
			const bool bBored = Now() - LastCombatTime > 18.f;
			const bool bTooFar = FVector::Dist2D(GetActorLocation(), HomeLocation) > 7000.f;
			if (bBored || bTooFar || !CombatTarget.IsValid())
			{
				ClearCombatTarget();
				Brain = ECreatureBrain::Return;
			}
		}
	}

	switch (Brain)
	{
	case ECreatureBrain::Idle:
		BrainTimer -= Dt;
		if (BrainTimer <= 0.f)
		{
			Brain = PickWanderDestination() ? ECreatureBrain::Wander : ECreatureBrain::Idle;
			BrainTimer = Brain == ECreatureBrain::Wander ? 12.f : 2.f;
		}
		break;

	case ECreatureBrain::Wander:
		BrainTimer -= Dt;
		if (MoveTowards(WanderTarget, 1.f, 150.f) || BrainTimer <= 0.f)
		{
			Brain = ECreatureBrain::Idle;
			BrainTimer = FMath::FRandRange(2.f, 7.f);
		}
		break;

	case ECreatureBrain::Flee:
		BrainTimer -= Dt;
		if (Player)
		{
			const FVector Away = (GetActorLocation() - Player->GetActorLocation()).GetSafeNormal2D();
			MoveTowards(GetActorLocation() + Away * 1000.f, 2.f, 0.f);
		}
		if (DistPlayer > 2600.f || BrainTimer <= 0.f)
		{
			Brain = ECreatureBrain::Idle;
			BrainTimer = 2.f;
			HomeLocation = GetActorLocation();
		}
		break;

	case ECreatureBrain::Fight:
		UpdateFight(Dt);
		break;

	case ECreatureBrain::Return:
		Heal(Stats.MaxHP * 0.04f * Dt);
		if (MoveTowards(HomeLocation, 1.f, 300.f))
		{
			Brain = ECreatureBrain::Idle;
			BrainTimer = 2.f;
		}
		break;

	default: break;
	}
}

// ---------------------------------------------------------------------------------------------
// IA : compagnon
// ---------------------------------------------------------------------------------------------

void ACreature::UpdateCompanion(float Dt)
{
	AAetherPlayerCharacter* T = Tamer.Get();
	if (!T) return;

	if (!CombatTarget.IsValid() && PerceptionTimer <= 0.f)
	{
		PerceptionTimer = 0.4f;
		// Defense automatique : on cible la creature sauvage qui attaque le dresseur ou ce compagnon.
		for (TActorIterator<ACreature> It(GetWorld()); It; ++It)
		{
			ACreature* C = *It;
			if (C->IsWild() && !C->IsFainted() && !C->IsBeingCaptured() &&
				(C->GetCombatTarget() == T || C->GetCombatTarget() == this) &&
				FVector::Dist(C->GetActorLocation(), GetActorLocation()) < 2500.f)
			{
				SetCombatTarget(C);
				break;
			}
		}
	}

	if (CombatTarget.IsValid())
	{
		UpdateFight(Dt);
		if (FVector::Dist(T->GetActorLocation(), GetActorLocation()) > 4500.f) ClearCombatTarget();
		return;
	}

	const FVector Behind = T->GetActorLocation() - T->GetActorForwardVector() * (220.f + GetBodyRadius())
		+ T->GetActorRightVector() * (160.f + GetBodyRadius());
	const float D = FVector::Dist2D(Behind, GetActorLocation());
	if (D > 6000.f)
	{
		bool bHit = false;
		const float G = GroundHeightAt(Behind + FVector(0, 0, 3000.f), bHit);
		SetActorLocation(FVector(Behind.X, Behind.Y, (bHit ? G : Behind.Z) + HalfHeight + 20.f), false, nullptr, ETeleportType::TeleportPhysics);
		return;
	}
	if (D > 200.f)
	{
		const float TamerSpeed = T->GetVelocity().Size2D();
		MoveTowards(Behind, (D > 900.f || TamerSpeed > 450.f) ? 2.f : 1.f, 120.f);
	}
}

// ---------------------------------------------------------------------------------------------
// Combat
// ---------------------------------------------------------------------------------------------

void ACreature::SetCombatTarget(AActor* Target, FName PreferredAbility)
{
	if (!Target || Target == this || IsFainted()) return;
	CombatTarget = Target;
	if (!PreferredAbility.IsNone()) PendingAbility = PreferredAbility;
	LastCombatTime = Now();
	if (Mode != ECreatureMode::Ridden) Brain = ECreatureBrain::Fight;
}

void ACreature::ClearCombatTarget()
{
	CombatTarget = nullptr;
	PendingAbility = NAME_None;
	if (Brain == ECreatureBrain::Fight)
	{
		Brain = (Mode == ECreatureMode::Wild) ? ECreatureBrain::Idle : ECreatureBrain::Follow;
	}
}

void ACreature::NotifyAttackedBy(AActor* Attacker)
{
	if (!Attacker || IsFainted()) return;
	LastAttacker = Attacker;
	LastCombatTime = Now();
	if (Mode == ECreatureMode::Wild)
	{
		if (Species.Temperament == ETemperament::Skittish && FMath::FRand() < 0.5f && GetHPFraction() < 0.6f)
		{
			Brain = ECreatureBrain::Flee;
			BrainTimer = 4.f;
		}
		else if (!CombatTarget.IsValid() || FMath::FRand() < 0.35f)
		{
			SetCombatTarget(Attacker);
		}
	}
	else if (Mode == ECreatureMode::Companion && !CombatTarget.IsValid())
	{
		SetCombatTarget(Attacker);
	}
}

bool ACreature::IsHostileTo(const AActor* Other) const
{
	if (!Other || Other == this) return false;
	if (const ACreature* C = Cast<ACreature>(Other))
	{
		if (C->IsFainted() || C->IsBeingCaptured()) return false;
		return (Mode == ECreatureMode::Wild) ? !C->IsWild() : C->IsWild();
	}
	if (Other->IsA<AAetherPlayerCharacter>()) return Mode == ECreatureMode::Wild;
	return false;
}

bool ACreature::IsAbilityReady(FName AbilityId) const
{
	const float* End = CooldownEnd.Find(AbilityId);
	return !End || Now() >= *End;
}

float ACreature::GetCooldownRemaining(FName AbilityId) const
{
	const float* End = CooldownEnd.Find(AbilityId);
	return End ? FMath::Max(0.f, *End - Now()) : 0.f;
}

float ACreature::GetCooldownFraction(FName AbilityId) const
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	const FAbilityDef* A = DB ? DB->FindAbility(AbilityId) : nullptr;
	if (!A || A->Cooldown <= 0.f) return 0.f;
	return FMath::Clamp(GetCooldownRemaining(AbilityId) / A->Cooldown, 0.f, 1.f);
}

FName ACreature::ChooseAbility(AActor* Target, float Distance) const
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	if (!DB) return NAME_None;
	TArray<FName> Options = Data.Abilities;
	if (Resonance >= 100.f && !Species.Ultimate.IsNone()) Options.Add(Species.Ultimate);
	const ACreature* TC = Cast<ACreature>(Target);

	FName Best;
	float BestScore = -1.f;
	for (const FName& Id : Options)
	{
		const FAbilityDef* A = DB->FindAbility(Id);
		if (!A) continue;
		float Score;
		if (A->Shape == EAbilityShape::Heal)
		{
			Score = GetHPFraction() < 0.4f ? 300.f : -1.f;
		}
		else if (A->Shape == EAbilityShape::Buff)
		{
			Score = (AttackBuff <= 1.f && Distance < 700.f) ? 55.f : -1.f;
		}
		else
		{
			const float Eff = TC ? Aether::EffectivenessVs(A->Element, TC->GetSpecies()) : 1.f;
			const float Stab = Species.HasElement(A->Element) ? 1.25f : 1.f;
			Score = A->Power * Eff * Stab * (A->bUltimate ? 2.5f : 1.f);
			if (Distance > A->Range) Score *= 0.6f;
			if (Mode == ECreatureMode::Wild) Score *= FMath::FRandRange(0.7f, 1.3f);
		}
		if (!IsAbilityReady(Id)) Score *= 0.05f;
		if (Score > BestScore)
		{
			BestScore = Score;
			Best = Id;
		}
	}
	return Best;
}

void ACreature::UpdateFight(float Dt)
{
	AActor* T = CombatTarget.Get();
	const ACreature* TC = Cast<ACreature>(T);
	const AAetherPlayerCharacter* TP = Cast<AAetherPlayerCharacter>(T);
	if (!T || (TC && (TC->IsFainted() || TC->IsBeingCaptured())) || (TP && TP->IsDowned()) || T->IsHidden())
	{
		ClearCombatTarget();
		return;
	}
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	const float TargetRadius = TC ? TC->GetBodyRadius() : 40.f;
	const float Dist = FMath::Max(0.f, FVector::Dist2D(T->GetActorLocation(), GetActorLocation()) - GetBodyRadius() - TargetRadius);

	FName Ability = (!PendingAbility.IsNone() && IsAbilityReady(PendingAbility)) ? PendingAbility : ChooseAbility(T, Dist);
	const FAbilityDef* A = DB ? DB->FindAbility(Ability) : nullptr;
	float Range = A ? A->Range : 150.f;
	if (A && A->Shape == EAbilityShape::Nova) Range = A->Radius * 0.75f;
	if (A && (A->Shape == EAbilityShape::Buff || A->Shape == EAbilityShape::Heal)) Range = 1e6f;

	if (Dist > Range)
	{
		MoveTowards(T->GetActorLocation(), 2.f, 0.f);
	}
	else
	{
		FaceTowards(T->GetActorLocation(), Dt);
		if (A && CanAct() && Now() >= GlobalCooldownEnd && IsAbilityReady(Ability))
		{
			if (TryUseAbility(Ability, T) && Ability == PendingAbility) PendingAbility = NAME_None;
		}
	}
}

bool ACreature::TryUseAbility(FName AbilityId, AActor* Target)
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	const FAbilityDef* A = DB ? DB->FindAbility(AbilityId) : nullptr;
	if (!A || !CanAct() || !IsAbilityReady(AbilityId) || Now() < GlobalCooldownEnd) return false;
	if (A->bUltimate && Resonance < 100.f) return false;

	const bool bNeedsTarget = A->Shape == EAbilityShape::Melee || A->Shape == EAbilityShape::Dash;
	if (bNeedsTarget)
	{
		if (!Target) return false;
		const float TR = Target->IsA<ACreature>() ? Cast<ACreature>(Target)->GetBodyRadius() : 40.f;
		const float Dist = FVector::Dist2D(Target->GetActorLocation(), GetActorLocation()) - GetBodyRadius() - TR;
		if (Dist > A->Range + 120.f)
		{
			if (Mode == ECreatureMode::Ridden) SpawnFloatingText(TEXT("Trop loin"), FLinearColor::Gray);
			return false;
		}
	}

	CooldownEnd.Add(AbilityId, Now() + A->Cooldown);
	GlobalCooldownEnd = Now() + 0.7f;
	if (A->bUltimate) Resonance = 0.f;
	LastCombatTime = Now();
	ExecuteAbility(*A, Target);
	return true;
}

void ACreature::ExecuteAbility(const FAbilityDef& A, AActor* Target)
{
	if (Target) FaceTowards(Target->GetActorLocation(), 1.f);
	PlayAnim(TEXT("Attack"), false);
	const UAnimSequence* AttackSeq = Anims.FindRef(TEXT("Attack"));
	AttackAnimEnd = Now() + (AttackSeq ? AttackSeq->GetPlayLength() : 0.6f);

	const FLinearColor Col = Aether::ElementColor(A.Element);
	const float Scale = A.VfxScale * (A.bUltimate ? 2.f : 1.f);
	if (A.bUltimate) SpawnFloatingText(A.DisplayName + TEXT(" !"), Aether::RarityColor(EAetherRarity::Legendary));

	TWeakObjectPtr<ACreature> WeakThis(this);
	TWeakObjectPtr<AActor> WeakTarget(Target);
	const FAbilityDef Ability = A;

	switch (A.Shape)
	{
	case EAbilityShape::Melee:
	{
		FTimerHandle H;
		GetWorldTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [WeakThis, WeakTarget, Ability, Col, Scale]()
		{
			ACreature* Self = WeakThis.Get();
			AActor* T = WeakTarget.Get();
			if (!Self || !T || Self->IsFainted()) return;
			const float Dist = FVector::Dist2D(T->GetActorLocation(), Self->GetActorLocation()) - Self->GetBodyRadius();
			if (Dist <= Ability.Range + 220.f)
			{
				AAetherVfx::SpawnBurst(Self->GetWorld(), T->GetActorLocation(), Col, 120.f * Scale, 0.35f);
				ResolveHit(Self, T, Ability);
			}
		}), 0.3f, false);
		break;
	}
	case EAbilityShape::Dash:
	{
		const FVector Dir = Target ? (Target->GetActorLocation() - GetActorLocation()).GetSafeNormal2D() : GetActorForwardVector();
		LaunchCharacter(Dir * 1500.f + FVector(0, 0, 150.f), true, false);
		AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), Col, 150.f * Scale, 0.4f);
		FTimerHandle H;
		GetWorldTimerManager().SetTimer(H, FTimerDelegate::CreateWeakLambda(this, [WeakThis, WeakTarget, Ability, Col, Scale]()
		{
			ACreature* Self = WeakThis.Get();
			AActor* T = WeakTarget.Get();
			if (!Self || !T) return;
			if (FVector::Dist2D(T->GetActorLocation(), Self->GetActorLocation()) < Ability.Range + Self->GetBodyRadius() + 250.f)
			{
				AAetherVfx::SpawnBurst(Self->GetWorld(), T->GetActorLocation(), Col, 180.f * Scale, 0.4f);
				ResolveHit(Self, T, Ability);
			}
		}), 0.35f, false);
		break;
	}
	case EAbilityShape::Projectile:
	{
		const FVector Start = GetActorLocation() + GetActorForwardVector() * (GetBodyRadius() + 40.f) + FVector(0, 0, HalfHeight * 0.4f);
		FVector Dir = GetActorForwardVector();
		if (Mode == ECreatureMode::Ridden && Controller) Dir = Controller->GetControlRotation().Vector();
		AAbilityProjectile::Launch(this, Start, Target, Dir, Ability);
		break;
	}
	case EAbilityShape::Nova:
	{
		AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), Col, A.Radius * Scale, 0.6f);
		TArray<AActor*> Victims;
		for (TActorIterator<ACreature> It(GetWorld()); It; ++It)
		{
			if (IsHostileTo(*It) && FVector::Dist(It->GetActorLocation(), GetActorLocation()) <= A.Radius + It->GetBodyRadius())
			{
				Victims.Add(*It);
			}
		}
		if (Mode == ECreatureMode::Wild)
		{
			if (ACharacter* P = UGameplayStatics::GetPlayerCharacter(this, 0))
			{
				if (FVector::Dist(P->GetActorLocation(), GetActorLocation()) <= A.Radius) Victims.Add(P);
			}
		}
		for (AActor* V : Victims) ResolveHit(this, V, A, 1.f);
		break;
	}
	case EAbilityShape::Buff:
		AttackBuff = 1.f + FMath::Max(0.2f, A.BuffAmount);
		AttackBuffEnd = Now() + 10.f;
		AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), Col, 200.f * Scale, 0.8f);
		SpawnFloatingText(TEXT("Attaque +"), Col);
		break;
	case EAbilityShape::Heal:
		Heal(Stats.MaxHP * FMath::Max(0.15f, A.BuffAmount));
		AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), FLinearColor(0.3f, 1.f, 0.4f), 220.f * Scale, 0.8f);
		break;
	}
}

void ACreature::ResolveHit(ACreature* Attacker, AActor* Victim, const FAbilityDef& A, float PowerScale)
{
	if (!Attacker || !Victim || !Attacker->IsHostileTo(Victim)) return;

	const float Acc = A.Accuracy * (Attacker->Status == EAetherStatus::Blinded ? 0.5f : 1.f);
	if (FMath::FRand() > Acc)
	{
		AAetherHUD::PushFloatingText(Attacker->GetWorld(), Victim->GetActorLocation() + FVector(0, 0, 120.f), TEXT("Esquive"), FLinearColor::Gray);
		return;
	}

	const float Atk = (A.bSpecial ? Attacker->Stats.Spirit : Attacker->Stats.Attack) * Attacker->AttackBuff;
	const float Stab = Attacker->Species.HasElement(A.Element) ? 1.25f : 1.f;
	const bool bCrit = FMath::FRand() < 0.07f;
	const float LevelMul = 1.f + Attacker->Data.Level / 22.f;
	const float Rand = FMath::FRandRange(0.9f, 1.1f);

	if (ACreature* VC = Cast<ACreature>(Victim))
	{
		const float Def = A.bSpecial ? VC->Stats.Spirit : VC->Stats.Defense;
		float Eff = Aether::EffectivenessVs(A.Element, VC->Species);
		if (VC->Status == EAetherStatus::Soaked && A.Element == EAetherElement::Storm) Eff *= 1.5f;
		const float Dmg = FMath::Max(1.f, A.Power * 0.32f * (Atk / FMath::Max(Def, 1.f)) * LevelMul * Stab * Eff * (bCrit ? 1.5f : 1.f) * Rand * PowerScale);
		VC->ReceiveHit(Attacker, A, Dmg, bCrit, Eff);
		if (A.Status != EAetherStatus::None && FMath::FRand() < A.StatusChance && !VC->IsFainted())
		{
			VC->ApplyStatus(A.Status, A.StatusDuration);
		}
	}
	else if (AAetherPlayerCharacter* P = Cast<AAetherPlayerCharacter>(Victim))
	{
		const float Dmg = FMath::Max(1.f, A.Power * 0.16f * (Atk / (12.f + P->GetTamerLevel() * 1.5f)) * LevelMul * Rand * PowerScale);
		P->ReceiveCreatureDamage(Dmg, Attacker);
	}
	Attacker->Resonance = FMath::Min(100.f, Attacker->Resonance + (bCrit ? 14.f : 8.f));
}

void ACreature::ReceiveHit(ACreature* Attacker, const FAbilityDef& A, float Damage, bool bCrit, float Eff)
{
	if (IsFainted() || IsBeingCaptured()) return;
	LastHitElement = A.Element;
	if (Status == EAetherStatus::Asleep) Status = EAetherStatus::None;
	if (Status == EAetherStatus::Frozen && A.Element == EAetherElement::Fire) Status = EAetherStatus::None;
	Resonance = FMath::Min(100.f, Resonance + 5.f);

	FString Txt = FString::Printf(TEXT("-%d"), FMath::RoundToInt(Damage));
	FLinearColor Col = FLinearColor::White;
	if (bCrit) { Txt += TEXT(" CRITIQUE"); Col = FLinearColor(1.f, 0.85f, 0.1f); }
	if (Eff > 1.01f) { Txt += TEXT("  Super efficace"); Col = FLinearColor(1.f, 0.5f, 0.1f); }
	else if (Eff < 0.99f) { Txt += TEXT("  Peu efficace"); Col = FLinearColor(0.6f, 0.6f, 0.6f); }
	SpawnFloatingText(Txt, Col);

	if (Attacker)
	{
		if (!Attacker->IsWild()) Participants.Add(Attacker);
		NotifyAttackedBy(Attacker);
	}
	ReceiveRawDamage(Damage, Attacker);
}

void ACreature::ReceiveRawDamage(float Damage, AActor* Source)
{
	if (IsFainted() || IsBeingCaptured()) return;
	Data.CurrentHP = FMath::Max(0.f, Data.CurrentHP - Damage);
	LastCombatTime = Now();
	SyncToTamer();
	if (Data.CurrentHP <= 0.f) Faint(Source);
}

void ACreature::ApplyStatus(EAetherStatus NewStatus, float Duration)
{
	if (NewStatus == EAetherStatus::None) return;
	if (NewStatus == EAetherStatus::Burn && Species.HasElement(EAetherElement::Fire)) return;
	if (NewStatus == EAetherStatus::Frozen && Species.HasElement(EAetherElement::Frost)) return;
	if (NewStatus == EAetherStatus::Soaked && Species.HasElement(EAetherElement::Water)) return;
	Status = NewStatus;
	StatusTimeLeft = Duration;
	BurnTick = 1.f;
	SpawnFloatingText(Aether::StatusName(NewStatus), FLinearColor(0.8f, 0.5f, 1.f));
	if (NewStatus == EAetherStatus::Frozen || NewStatus == EAetherStatus::Stunned || NewStatus == EAetherStatus::Asleep || NewStatus == EAetherStatus::Rooted)
	{
		GetCharacterMovement()->StopMovementImmediately();
	}
}

void ACreature::Heal(float Amount)
{
	if (IsFainted()) return;
	Data.CurrentHP = FMath::Min(Stats.MaxHP, Data.CurrentHP + Amount);
	SyncToTamer();
}

void ACreature::FullRestore()
{
	Data.CurrentHP = Stats.MaxHP;
	Status = EAetherStatus::None;
	SyncToTamer();
}

void ACreature::Faint(AActor* Killer)
{
	if (Brain == ECreatureBrain::Fainted) return;
	Brain = ECreatureBrain::Fainted;
	FaintTime = Now();
	Data.CurrentHP = 0.f;
	Status = EAetherStatus::None;
	CombatTarget = nullptr;
	GetCharacterMovement()->StopMovementImmediately();
	GetCharacterMovement()->DisableMovement();
	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	SpawnFloatingText(TEXT("K.O."), FLinearColor(1.f, 0.3f, 0.3f));
	if (!bUsesAnimBlueprint)
	{
		if (UAnimSequence* Idle = Anims.FindRef(TEXT("Idle"))) GetMesh()->PlayAnimation(Idle, false);
		GetMesh()->SetPlayRate(0.2f);
	}

	if (Mode == ECreatureMode::Wild)
	{
		const int32 XP = FMath::Max(5, Species.BaseXP * Data.Level / 5);
		AAetherPlayerCharacter* Winner = nullptr;
		for (const TWeakObjectPtr<ACreature>& P : Participants)
		{
			if (ACreature* C = P.Get())
			{
				if (!C->IsFainted()) C->GainXP(XP);
				if (!Winner) Winner = C->GetTamer() ? C->GetTamer() : C->GetRider();
			}
		}
		if (!Winner) Winner = Cast<AAetherPlayerCharacter>(Killer);
		if (Winner) Winner->OnWildDefeated(this, XP);
		SetLifeSpan(3.f);
	}
	else
	{
		SyncToTamer();
		if (AAetherPlayerCharacter* R = Rider.Get()) R->Dismount();
		if (AAetherPlayerCharacter* T = Tamer.Get()) T->OnCompanionFainted(this);
	}
}

void ACreature::UpdateFaint(float Dt)
{
	const float T = Now() - FaintTime;
	if (Mode == ECreatureMode::Wild && T > 1.2f)
	{
		const float S = FMath::Max(0.01f, 1.f - (T - 1.2f) / 1.6f);
		GetMesh()->SetRelativeScale3D(FVector(MeshBaseScale * S));
		FallbackBody->SetRelativeScale3D(FallbackBody->GetRelativeScale3D() * FMath::Max(0.9f, 1.f - Dt * 3.f));
	}
}

// ---------------------------------------------------------------------------------------------
// Capture
// ---------------------------------------------------------------------------------------------

void ACreature::BeginCaptureAbsorb()
{
	Brain = ECreatureBrain::Captured;
	CombatTarget = nullptr;
	SetActorHiddenInGame(true);
	SetActorEnableCollision(false);
	GetCharacterMovement()->StopMovementImmediately();
	GetCharacterMovement()->DisableMovement();
	Glow->SetVisibility(false);
}

void ACreature::EndCaptureEscape()
{
	++CaptureEscapes;
	SetActorHiddenInGame(false);
	SetActorEnableCollision(true);
	SetupMovement();
	Brain = ECreatureBrain::Idle;
	SpawnFloatingText(TEXT("S'est echappe !"), FLinearColor(1.f, 0.4f, 0.2f));
	if (ACharacter* P = UGameplayStatics::GetPlayerCharacter(this, 0))
	{
		AAetherPlayerCharacter* AP = Cast<AAetherPlayerCharacter>(P);
		ACreature* Comp = AP ? AP->GetActiveCompanion() : nullptr;
		SetCombatTarget(Comp ? static_cast<AActor*>(Comp) : static_cast<AActor*>(P));
	}
}

// ---------------------------------------------------------------------------------------------
// Monture
// ---------------------------------------------------------------------------------------------

bool ACreature::CanBeRidden() const
{
	return Species.bRideable && Mode == ECreatureMode::Companion && !IsFainted();
}

void ACreature::OnMounted(AAetherPlayerCharacter* InRider)
{
	Rider = InRider;
	Mode = ECreatureMode::Ridden;
	CombatTarget = nullptr;
	Brain = ECreatureBrain::Idle;
	bRiderFlying = false;
	if (!bSwimming) GetCharacterMovement()->SetMovementMode(MOVE_Walking);
	SpawnFloatingText(Species.CanFly() ? TEXT("Espace : decoller") : TEXT("En selle !"), FLinearColor::White);
}

void ACreature::OnDismounted()
{
	Rider = nullptr;
	Mode = ECreatureMode::Companion;
	bRiderFlying = false;
	bRiderSprint = false;
	RiderVerticalInput = 0.f;
	Brain = ECreatureBrain::Follow;
	SetupMovement();
}

void ACreature::RiderMove(const FVector2D& Input)
{
	if (!Controller || !CanAct()) return;
	const FRotator Yaw(0.f, Controller->GetControlRotation().Yaw, 0.f);
	const FVector Fwd = FRotationMatrix(Yaw).GetUnitAxis(EAxis::X);
	const FVector Right = FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y);
	AddMovementInput(Fwd, Input.Y);
	AddMovementInput(Right, Input.X);
	if (bRiderFlying)
	{
		// en vol on suit aussi le tangage de la camera
		const float Pitch = FRotator::NormalizeAxis(Controller->GetControlRotation().Pitch);
		AddMovementInput(FVector::UpVector, FMath::Clamp(Pitch / 45.f, -1.f, 1.f) * Input.Y * 0.6f);
	}
}

void ACreature::RiderVertical(float Value)
{
	RiderVerticalInput = Value;
	if (bRiderFlying || bSwimming) AddMovementInput(FVector::UpVector, Value);
}

void ACreature::RiderJump()
{
	if (Species.CanFly())
	{
		if (!bRiderFlying)
		{
			bRiderFlying = true;
			bSwimming = false;
			GetCharacterMovement()->SetMovementMode(MOVE_Flying);
			LaunchCharacter(FVector(0, 0, 700.f), false, true);
		}
		return;
	}
	Jump();
}

// ---------------------------------------------------------------------------------------------
// Progression
// ---------------------------------------------------------------------------------------------

void ACreature::GainXP(int32 Amount)
{
	if (Mode == ECreatureMode::Wild || Amount <= 0) return;
	UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	Data.XP += Amount;
	Data.Bond = FMath::Min(255, Data.Bond + 1);
	bool bLevelUp = false;
	while (Data.Level < 100 && Data.XP >= Aether::XPForNextLevel(Data.Level))
	{
		Data.XP -= Aether::XPForNextLevel(Data.Level);
		++Data.Level;
		bLevelUp = true;
		if (DB)
		{
			for (const FName& L : DB->LearnAbilitiesForLevel(Data, Data.Level))
			{
				const FAbilityDef* A = DB->FindAbility(L);
				if (AAetherPlayerCharacter* T = Tamer.Get())
				{
					T->Notify(FString::Printf(TEXT("%s apprend %s !"), *GetDisplayName(), A ? *A->DisplayName : *L.ToString()), Aether::ElementColor(A ? A->Element : EAetherElement::Neutral));
				}
			}
		}
	}
	if (bLevelUp)
	{
		const float Frac = GetHPFraction();
		Stats = Aether::ComputeStats(Species, Data);
		Data.CurrentHP = FMath::Min(Stats.MaxHP, Stats.MaxHP * Frac + Stats.MaxHP * 0.2f);
		SpawnFloatingText(FString::Printf(TEXT("Niveau %d !"), Data.Level), FLinearColor(0.4f, 1.f, 0.5f));
		if (AAetherPlayerCharacter* T = Tamer.Get())
		{
			T->Notify(FString::Printf(TEXT("%s passe au niveau %d"), *GetDisplayName(), Data.Level), FLinearColor(0.4f, 1.f, 0.5f));
		}
	}
	SyncToTamer();
	if (bLevelUp && !Species.EvolvesTo.IsNone() && Species.EvolveLevel > 0 && Data.Level >= Species.EvolveLevel)
	{
		if (AAetherPlayerCharacter* T = Tamer.Get()) T->RequestEvolution(this);
	}
}

void ACreature::SyncToTamer()
{
	if (Mode == ECreatureMode::Wild) return;
	AAetherPlayerCharacter* T = Tamer.Get();
	if (T && T->GetCollection()) T->GetCollection()->SyncFromCompanion(Data);
}

// ---------------------------------------------------------------------------------------------
// Animation
// ---------------------------------------------------------------------------------------------

void ACreature::PlayAnim(FName Key, bool bLoop, float Rate)
{
	if (bUsesAnimBlueprint)
	{
		// la locomotion est geree par l'Animation Blueprint ; on ne joue que les actions (attaque) en montage
		if (!bLoop)
		{
			UAnimSequence* Act = Anims.FindRef(Key);
			if (UAnimInstance* AI = GetMesh()->GetAnimInstance())
			{
				if (Act) AI->PlaySlotAnimationAsDynamicMontage(Act, TEXT("DefaultSlot"), 0.12f, 0.2f, Rate);
			}
		}
		return;
	}
	UAnimSequence* Seq = Anims.FindRef(Key);
	if (!Seq && Key == TEXT("Run")) { Key = TEXT("Walk"); Seq = Anims.FindRef(Key); Rate *= 1.6f; }
	if (!Seq && (Key == TEXT("Fly") || Key == TEXT("Swim"))) { Key = TEXT("Walk"); Seq = Anims.FindRef(Key); }
	if (!Seq) { Key = TEXT("Idle"); Seq = Anims.FindRef(Key); }
	if (!Seq) return;
	if (CurrentAnim != Key || !bLoop)
	{
		GetMesh()->PlayAnimation(Seq, bLoop);
		CurrentAnim = bLoop ? Key : NAME_None;
	}
	GetMesh()->SetPlayRate(Rate);
}

bool ACreature::IsFlyingNow() const
{
	return GetCharacterMovement()->MovementMode == MOVE_Flying && !bSwimming;
}

void ACreature::UpdateAnimation(float Dt)
{
	if (bUsesAnimBlueprint) return;
	if (Anims.Num() == 0)
	{
		// forme de secours : petit rebond procedural
		const float Speed = GetVelocity().Size2D();
		const float Bob = FMath::Abs(FMath::Sin(Now() * 10.f)) * FMath::Clamp(Speed / 400.f, 0.f, 1.f) * 12.f;
		FallbackBody->SetRelativeLocation(FVector(0, 0, Bob));
		return;
	}
	if (Now() < AttackAnimEnd) return;

	const float Speed = GetVelocity().Size2D();
	const bool bFly = GetCharacterMovement()->MovementMode == MOVE_Flying && !bSwimming;
	if (bSwimming)
	{
		PlayAnim(TEXT("Swim"), true, FMath::Clamp(Speed / FMath::Max(1.f, Species.WalkSpeed), 0.6f, 1.8f));
	}
	else if (bFly)
	{
		PlayAnim(TEXT("Fly"), true, FMath::Clamp(0.8f + Speed / 1500.f, 0.8f, 1.6f));
	}
	else if (Speed > Species.WalkSpeed * 1.35f)
	{
		PlayAnim(TEXT("Run"), true, FMath::Clamp(Speed / FMath::Max(1.f, Species.RunSpeed), 0.6f, 1.8f));
	}
	else if (Speed > 15.f)
	{
		PlayAnim(TEXT("Walk"), true, FMath::Clamp(Speed / FMath::Max(1.f, Species.WalkSpeed), 0.5f, 2.f));
	}
	else
	{
		PlayAnim(TEXT("Idle"), true, 1.f);
	}
}

void ACreature::SpawnFloatingText(const FString& Text, const FLinearColor& Color) const
{
	AAetherHUD::PushFloatingText(GetWorld(), GetActorLocation() + FVector(0, 0, HalfHeight + 60.f), Text, Color);
}
