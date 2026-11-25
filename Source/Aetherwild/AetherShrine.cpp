#include "AetherShrine.h"

#include "AbilityEffects.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

AAetherShrine::AAetherShrine()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.05f;

	Base = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Base"));
	RootComponent = Base;
	Base->SetMobility(EComponentMobility::Movable);
	Crystal = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Crystal"));
	Crystal->SetupAttachment(Base);
	Crystal->SetMobility(EComponentMobility::Movable);
	Crystal->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	// Formes de base ; remplacees au BeginPlay par le modele Blender s'il a ete importe.
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cyl(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cone(TEXT("/Engine/BasicShapes/Cone.Cone"));
	if (Cyl.Succeeded()) Base->SetStaticMesh(Cyl.Object);
	Base->SetRelativeScale3D(FVector(4.f, 4.f, 0.5f));
	if (Cone.Succeeded()) Crystal->SetStaticMesh(Cone.Object);
	Crystal->SetRelativeLocation(FVector(0, 0, 250.f));
	Crystal->SetRelativeScale3D(FVector(0.2f / 4.f, 0.2f / 4.f, 4.f / 0.5f));

	Light = CreateDefaultSubobject<UPointLightComponent>(TEXT("Light"));
	Light->SetupAttachment(Base);
	Light->SetRelativeLocation(FVector(0, 0, 300.f));
	Light->SetIntensityUnits(ELightUnits::Candelas);
	Light->SetIntensity(150.f);
	Light->SetAttenuationRadius(2500.f);
	Light->SetLightColor(FLinearColor(0.45f, 0.9f, 1.f));
	Light->SetCastShadows(false);
}

void AAetherShrine::BeginPlay()
{
	Super::BeginPlay();
	if (UStaticMesh* ShrineMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Aetherwild/Environment/SM_Shrine.SM_Shrine"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		Base->SetStaticMesh(ShrineMesh);
		Base->SetWorldScale3D(FVector(1.f));
		Crystal->SetVisibility(false);
	}
	else if (Crystal->GetStaticMesh())
	{
		if (UMaterialInterface* M = AAetherVfx::GetGlowMaterial())
		{
			UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(M, this);
			MID->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.45f, 0.9f, 1.f) * 8.f);
			MID->SetScalarParameterValue(TEXT("Opacity"), 0.9f);
			Crystal->SetMaterial(0, MID);
		}
	}
}

void AAetherShrine::Tick(float Dt)
{
	Super::Tick(Dt);
	Phase += Dt;
	Light->SetIntensity(120.f + 60.f * FMath::Sin(Phase * 1.7f));
	Crystal->SetRelativeRotation(FRotator(0.f, Phase * 25.f, 0.f));
}
