#include "AbilityEffects.h"

#include "Creature.h"
#include "AetherPlayerCharacter.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	UStaticMesh* GSphereMesh = nullptr;
	UMaterialInterface* GFallbackMat = nullptr;

	void SetupGlowSphere(UStaticMeshComponent* Sphere)
	{
		Sphere->SetMobility(EComponentMobility::Movable);
		Sphere->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Sphere->SetCastShadow(false);
		Sphere->bAffectDistanceFieldLighting = false;
		Sphere->SetGenerateOverlapEvents(false);
	}
}

UMaterialInterface* AAetherVfx::GetGlowMaterial()
{
	static TWeakObjectPtr<UMaterialInterface> Cached;
	if (!Cached.IsValid())
	{
		Cached = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Aetherwild/Materials/M_AetherGlow.M_AetherGlow"), nullptr, LOAD_NoWarn | LOAD_Quiet);
		if (!Cached.IsValid()) Cached = GFallbackMat;
	}
	return Cached.Get();
}

AAetherVfx::AAetherVfx()
{
	PrimaryActorTick.bCanEverTick = true;
	Sphere = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Sphere"));
	RootComponent = Sphere;
	SetupGlowSphere(Sphere);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (SphereMesh.Succeeded()) { GSphereMesh = SphereMesh.Object; Sphere->SetStaticMesh(GSphereMesh); }
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> BasicMat(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (BasicMat.Succeeded()) GFallbackMat = BasicMat.Object;

	Light = CreateDefaultSubobject<UPointLightComponent>(TEXT("Light"));
	Light->SetupAttachment(Sphere);
	Light->SetIntensityUnits(ELightUnits::Candelas);
	Light->SetCastShadows(false);
	Light->SetIntensity(200.f);
	InitialLifeSpan = 5.f;
}

AAetherVfx* AAetherVfx::SpawnBurst(UWorld* World, const FVector& Location, const FLinearColor& InColor, float InRadius, float InDuration)
{
	if (!World) return nullptr;
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AAetherVfx* V = World->SpawnActor<AAetherVfx>(AAetherVfx::StaticClass(), Location, FRotator::ZeroRotator, P);
	if (!V) return nullptr;
	V->Color = InColor;
	V->Radius = InRadius;
	V->Duration = FMath::Max(0.1f, InDuration);
	if (UMaterialInterface* M = GetGlowMaterial())
	{
		V->MID = UMaterialInstanceDynamic::Create(M, V);
		V->MID->SetVectorParameterValue(TEXT("Color"), InColor * 6.f);
		V->Sphere->SetMaterial(0, V->MID);
	}
	V->Light->SetLightColor(InColor);
	V->Light->SetAttenuationRadius(InRadius * 4.f);
	V->Sphere->SetWorldScale3D(FVector(InRadius / 50.f * 0.2f));
	V->SetLifeSpan(V->Duration + 0.1f);
	return V;
}

void AAetherVfx::Tick(float Dt)
{
	Super::Tick(Dt);
	Age += Dt;
	const float T = FMath::Clamp(Age / Duration, 0.f, 1.f);
	const float Ease = 1.f - FMath::Pow(1.f - T, 3.f);
	Sphere->SetWorldScale3D(FVector(Radius / 50.f * FMath::Lerp(0.2f, 1.f, Ease)));
	const float Fade = 1.f - T;
	if (MID)
	{
		MID->SetScalarParameterValue(TEXT("Opacity"), Fade * 0.8f);
		MID->SetVectorParameterValue(TEXT("Color"), Color * 6.f * Fade);
	}
	Light->SetIntensity(200.f * Fade * FMath::Clamp(Radius / 150.f, 0.5f, 4.f));
}

// ------------------------------------------------------------------------------------------------

AAbilityProjectile::AAbilityProjectile()
{
	PrimaryActorTick.bCanEverTick = true;
	Sphere = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Sphere"));
	RootComponent = Sphere;
	SetupGlowSphere(Sphere);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (SphereMesh.Succeeded()) Sphere->SetStaticMesh(SphereMesh.Object);

	Light = CreateDefaultSubobject<UPointLightComponent>(TEXT("Light"));
	Light->SetupAttachment(Sphere);
	Light->SetIntensityUnits(ELightUnits::Candelas);
	Light->SetIntensity(120.f);
	Light->SetAttenuationRadius(500.f);
	Light->SetCastShadows(false);
	InitialLifeSpan = 4.f;
}

AAbilityProjectile* AAbilityProjectile::Launch(ACreature* Owner, const FVector& Start, AActor* InTarget, const FVector& Direction, const FAbilityDef& InAbility)
{
	if (!Owner) return nullptr;
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	P.Owner = Owner;
	AAbilityProjectile* Proj = Owner->GetWorld()->SpawnActor<AAbilityProjectile>(AAbilityProjectile::StaticClass(), Start, Direction.Rotation(), P);
	if (!Proj) return nullptr;
	Proj->Caster = Owner;
	Proj->Target = InTarget;
	Proj->Ability = InAbility;
	Proj->Velocity = Direction.GetSafeNormal() * Proj->Speed;
	const FLinearColor Col = Aether::ElementColor(InAbility.Element);
	const float Size = 0.35f * InAbility.VfxScale * (InAbility.bUltimate ? 2.2f : 1.f);
	Proj->Sphere->SetWorldScale3D(FVector(Size));
	if (UMaterialInterface* M = AAetherVfx::GetGlowMaterial())
	{
		Proj->MID = UMaterialInstanceDynamic::Create(M, Proj);
		Proj->MID->SetVectorParameterValue(TEXT("Color"), Col * 8.f);
		Proj->MID->SetScalarParameterValue(TEXT("Opacity"), 0.9f);
		Proj->Sphere->SetMaterial(0, Proj->MID);
	}
	Proj->Light->SetLightColor(Col);
	return Proj;
}

void AAbilityProjectile::Tick(float Dt)
{
	Super::Tick(Dt);
	Age += Dt;
	ACreature* C = Caster.Get();
	if (!C)
	{
		Destroy();
		return;
	}

	if (AActor* T = Target.Get())
	{
		const FVector Aim = T->GetActorLocation() + FVector(0, 0, 30.f);
		const FVector Desired = (Aim - GetActorLocation()).GetSafeNormal() * Speed;
		Velocity = FMath::VInterpTo(Velocity, Desired, Dt, 6.f);
		const float HitDist = (T->IsA<ACreature>() ? Cast<ACreature>(T)->GetBodyRadius() : 40.f) + 70.f;
		if (FVector::Dist(Aim, GetActorLocation()) < HitDist)
		{
			Impact(T);
			return;
		}
	}
	else
	{
		// tir libre (monture) : touche la premiere creature hostile sur la trajectoire
		for (TActorIterator<ACreature> It(GetWorld()); It; ++It)
		{
			if (C->IsHostileTo(*It) && FVector::Dist(It->GetActorLocation(), GetActorLocation()) < It->GetBodyRadius() + 80.f)
			{
				Impact(*It);
				return;
			}
		}
	}

	SetActorLocation(GetActorLocation() + Velocity * Dt);
	if (Age > 3.f || FVector::Dist(GetActorLocation(), C->GetActorLocation()) > Ability.Range * 1.8f + 1500.f)
	{
		AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), Aether::ElementColor(Ability.Element), 80.f, 0.3f);
		Destroy();
	}
}

void AAbilityProjectile::Impact(AActor* Victim)
{
	const float R = (Ability.bUltimate ? 260.f : 140.f) * Ability.VfxScale;
	AAetherVfx::SpawnBurst(GetWorld(), GetActorLocation(), Aether::ElementColor(Ability.Element), R, 0.45f);
	if (ACreature* C = Caster.Get())
	{
		ACreature::ResolveHit(C, Victim, Ability);
	}
	Destroy();
}
