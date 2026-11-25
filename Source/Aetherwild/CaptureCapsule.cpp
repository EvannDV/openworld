#include "CaptureCapsule.h"

#include "AbilityEffects.h"
#include "AetherHUD.h"
#include "AetherPlayerCharacter.h"
#include "AetherWorldSubsystem.h"
#include "Creature.h"
#include "CreatureCollectionComponent.h"

#include "Components/PointLightComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "TimerManager.h"
#include "UObject/ConstructorHelpers.h"

ACaptureCapsule::ACaptureCapsule()
{
	PrimaryActorTick.bCanEverTick = true;

	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	Collision->InitSphereRadius(12.f);
	Collision->SetCollisionProfileName(TEXT("BlockAllDynamic"));
	Collision->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	Collision->SetNotifyRigidBodyCollision(true);
	RootComponent = Collision;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylMesh(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));

	Shell = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Shell"));
	Shell->SetupAttachment(Collision);
	Shell->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Shell->SetRelativeScale3D(FVector(0.24f));
	if (SphereMesh.Succeeded()) Shell->SetStaticMesh(SphereMesh.Object);

	Band = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Band"));
	Band->SetupAttachment(Collision);
	Band->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Band->SetRelativeScale3D(FVector(0.255f, 0.255f, 0.04f));
	if (CylMesh.Succeeded()) Band->SetStaticMesh(CylMesh.Object);

	Light = CreateDefaultSubobject<UPointLightComponent>(TEXT("Light"));
	Light->SetupAttachment(Collision);
	Light->SetIntensityUnits(ELightUnits::Candelas);
	Light->SetIntensity(25.f);
	Light->SetAttenuationRadius(350.f);
	Light->SetCastShadows(false);

	Movement = CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("Movement"));
	Movement->UpdatedComponent = Collision;
	Movement->InitialSpeed = 0.f;
	Movement->MaxSpeed = 5000.f;
	Movement->ProjectileGravityScale = 1.f;
	Movement->bShouldBounce = true;
	Movement->Bounciness = 0.35f;
	Movement->Friction = 0.6f;
	Movement->bRotationFollowsVelocity = false;

	InitialLifeSpan = 25.f;
}

void ACaptureCapsule::Throw(AAetherPlayerCharacter* InThrower, ECapsuleTier InTier, const FVector& Velocity)
{
	Thrower = InThrower;
	Tier = InTier;
	Collision->IgnoreActorWhenMoving(InThrower, true);
	Collision->OnComponentHit.AddDynamic(this, &ACaptureCapsule::OnHit);
	Movement->Velocity = Velocity;
	const FLinearColor Col = Aether::CapsuleColor(Tier);
	if (UMaterialInterface* M = AAetherVfx::GetGlowMaterial())
	{
		UMaterialInstanceDynamic* BandMID = UMaterialInstanceDynamic::Create(M, this);
		BandMID->SetVectorParameterValue(TEXT("Color"), Col * 10.f);
		BandMID->SetScalarParameterValue(TEXT("Opacity"), 1.f);
		Band->SetMaterial(0, BandMID);
	}
	if (UMaterialInterface* Basic = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial")))
	{
		UMaterialInstanceDynamic* ShellMID = UMaterialInstanceDynamic::Create(Basic, this);
		ShellMID->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.85f, 0.88f, 0.92f));
		Shell->SetMaterial(0, ShellMID);
	}
	Light->SetLightColor(Col);
}

float ACaptureCapsule::ComputeCaptureChance(const ACreature* Target, ECapsuleTier InTier, int32 TamerLevel, FString& OutReason)
{
	if (!Target || !Target->IsWild() || Target->IsFainted()) { OutReason = TEXT("Impossible"); return 0.f; }
	const FSpeciesDef& S = Target->GetSpecies();
	const FCaptureRules& R = S.Capture;
	const UAetherWorldSubsystem* WS = UAetherWorldSubsystem::Get(Target);
	const float HPFrac = Target->GetHPFraction();

	auto Fail = [&OutReason, &R](const FString& Why)
	{
		OutReason = R.Hint.IsEmpty() ? Why : FString::Printf(TEXT("%s  (%s)"), *Why, *R.Hint);
		return 0.f;
	};
	if (TamerLevel < R.MinTamerLevel) return Fail(FString::Printf(TEXT("Niveau de dresseur %d requis"), R.MinTamerLevel));
	if (WS && !WS->MatchesPhase(R.Phase)) return Fail(FString::Printf(TEXT("Ne se laisse capturer que : %s"), *Aether::PhaseName(R.Phase)));
	if (WS && !WS->MatchesWeather(R.Weathers))
	{
		FString W;
		for (EWeatherType T : R.Weathers) W += (W.IsEmpty() ? TEXT("") : TEXT(" / ")) + Aether::WeatherName(T);
		return Fail(FString::Printf(TEXT("Meteo requise : %s"), *W));
	}
	if (R.WeakenedBy != EAetherElement::Neutral && Target->LastHitElement != R.WeakenedBy)
	{
		return Fail(FString::Printf(TEXT("Doit etre affaibli par une attaque %s"), *Aether::ElementName(R.WeakenedBy)));
	}
	if (HPFrac > R.MaxHealthFraction) return Fail(FString::Printf(TEXT("Trop vigoureux : PV sous %d%%"), FMath::RoundToInt(R.MaxHealthFraction * 100.f)));
	if (R.bRequiresStatus && Target->Status == EAetherStatus::None) return Fail(TEXT("Doit subir une alteration d'etat"));

	OutReason.Reset();
	const float HPTerm = 1.f - 0.8f * HPFrac;
	float StatusMul = 1.f;
	if (Target->Status == EAetherStatus::Asleep || Target->Status == EAetherStatus::Frozen) StatusMul = 2.f;
	else if (Target->Status != EAetherStatus::None) StatusMul = 1.4f;
	const float LevelTerm = FMath::Clamp(1.f - (Target->GetData().Level - TamerLevel * 3) * 0.02f, 0.4f, 1.2f);
	const float Resist = FMath::Max(0.4f, 1.f - 0.1f * Target->GetCaptureEscapes());
	float C = S.CatchRate * HPTerm * Aether::CapsuleMultiplier(InTier) * StatusMul * LevelTerm * Resist;
	if (InTier == ECapsuleTier::Prism && S.Rarity != EAetherRarity::Legendary) C = FMath::Max(C, 0.9f);
	return FMath::Clamp(C, 0.01f, 0.99f);
}

void ACaptureCapsule::OnHit(UPrimitiveComponent* HitComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit)
{
	if (bCapturing || bDone) return;
	if (ACreature* C = Cast<ACreature>(OtherActor))
	{
		if (C->IsWild() && !C->IsFainted() && !C->IsBeingCaptured())
		{
			StartCapture(C);
		}
	}
}

void ACaptureCapsule::StartCapture(ACreature* Target)
{
	AAetherPlayerCharacter* T = Thrower.Get();
	FString Reason;
	Chance = ComputeCaptureChance(Target, Tier, T ? T->GetTamerLevel() : 1, Reason);
	if (Chance <= 0.f)
	{
		AAetherHUD::PushFloatingText(GetWorld(), Target->GetActorLocation() + FVector(0, 0, 150.f), TEXT("Rejete !"), FLinearColor(1.f, 0.3f, 0.3f));
		if (T) T->Notify(FString::Printf(TEXT("%s repousse la capsule. %s"), *Target->GetDisplayName(), *Reason), FLinearColor(1.f, 0.55f, 0.3f));
		Target->NotifyAttackedBy(T);
		AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), FLinearColor(1.f, 0.2f, 0.2f), 90.f, 0.3f);
		bDone = true;
		SetLifeSpan(0.5f);
		return;
	}

	bCapturing = true;
	Captive = Target;
	Target->BeginCaptureAbsorb();
	AAetherVfx::SpawnBurst(GetWorld(), Target->GetActorLocation(), Aether::CapsuleColor(Tier), Target->GetBodyRadius() * 2.f + 60.f, 0.6f);

	// pose la capsule au sol a l'endroit de la creature
	Movement->StopMovementImmediately();
	Movement->ProjectileGravityScale = 0.f;
	Movement->SetUpdatedComponent(nullptr);
	FVector Ground = Target->GetActorLocation();
	FHitResult G;
	FCollisionQueryParams P(SCENE_QUERY_STAT(CapsuleGround), false, this);
	if (GetWorld()->LineTraceSingleByObjectType(G, Ground + FVector(0, 0, 200.f), Ground - FVector(0, 0, 3000.f), FCollisionObjectQueryParams(ECC_WorldStatic), P))
	{
		Ground = G.ImpactPoint + FVector(0, 0, 12.f);
	}
	Collision->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SetActorLocation(Ground);
	SetLifeSpan(0.f);
	Shakes = 0;
	GetWorldTimerManager().SetTimer(ShakeTimer, this, &ACaptureCapsule::DoShake, 1.0f, true, 1.0f);
	if (T) T->OnCaptureStarted(Target, Chance);
}

void ACaptureCapsule::DoShake()
{
	ACreature* C = Captive.Get();
	if (!C) { Finish(false); return; }
	// trois secousses : chacune doit reussir (probabilite = Chance^(1/3))
	const float PerShake = FMath::Pow(Chance, 1.f / 3.f);
	if (FMath::FRand() > PerShake)
	{
		Finish(false);
		return;
	}
	++Shakes;
	ShakeAnim = 0.45f;
	AAetherHUD::PushFloatingText(GetWorld(), GetActorLocation() + FVector(0, 0, 60.f), FString::ChrN(Shakes, TEXT('*')), Aether::CapsuleColor(Tier));
	if (Shakes >= 3) Finish(true);
}

void ACaptureCapsule::Finish(bool bSuccess)
{
	GetWorldTimerManager().ClearTimer(ShakeTimer);
	bDone = true;
	ACreature* C = Captive.Get();
	AAetherPlayerCharacter* T = Thrower.Get();
	if (bSuccess && C)
	{
		AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), FLinearColor(1.f, 0.9f, 0.4f), 220.f, 0.9f);
		if (T) T->OnCaptureSuccess(C, Tier);
		C->Destroy();
	}
	else if (C)
	{
		AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), Aether::CapsuleColor(Tier), 200.f, 0.4f);
		C->EndCaptureEscape();
		if (T) T->OnCaptureFailed(C);
	}
	SetLifeSpan(0.3f);
}

void ACaptureCapsule::Tick(float Dt)
{
	Super::Tick(Dt);
	if (bCapturing && !bDone)
	{
		ShakeAnim = FMath::Max(0.f, ShakeAnim - Dt);
		const float Wobble = FMath::Sin(ShakeAnim * 40.f) * ShakeAnim * 60.f;
		SetActorRotation(FRotator(0.f, 0.f, Wobble));
		Light->SetIntensity(25.f + 40.f * FMath::Abs(FMath::Sin(GetWorld()->GetTimeSeconds() * 6.f)));
		return;
	}
	if (!bCapturing && !bDone && Movement->Velocity.SizeSquared() < 100.f)
	{
		IdleTime += Dt;
		if (IdleTime > 1.5f)
		{
			// rate : la capsule revient dans la poche
			if (AAetherPlayerCharacter* T = Thrower.Get())
			{
				if (T->GetCollection()) T->GetCollection()->AddCapsules(Tier, 1);
			}
			AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), Aether::CapsuleColor(Tier), 60.f, 0.3f);
			bDone = true;
			Destroy();
		}
	}
}
