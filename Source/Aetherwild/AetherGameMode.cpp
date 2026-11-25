#include "AetherGameMode.h"

#include "AetherHUD.h"
#include "AetherPlayerCharacter.h"
#include "AetherPlayerController.h"
#include "AetherShrine.h"
#include "CreatureDatabase.h"
#include "CreatureSpawner.h"
#include "WorldScatter.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/VolumetricCloudComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/SkyLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"

AAetherGameMode::AAetherGameMode()
{
	DefaultPawnClass = AAetherPlayerCharacter::StaticClass();
	PlayerControllerClass = AAetherPlayerController::StaticClass();
	HUDClass = AAetherHUD::StaticClass();
}

UClass* AAetherGameMode::GetDefaultPawnClassForController_Implementation(AController* InController)
{
	// Permet un pion Blueprint (ex. dresseur MetaHuman) declare dans species.json -> player.blueprint
	if (const UCreatureDatabase* DB = UCreatureDatabase::Get(this)) return DB->GetPlayerPawnClass();
	return Super::GetDefaultPawnClassForController_Implementation(InController);
}

void AAetherGameMode::StartPlay()
{
	if (bSpawnFallbackSky) SpawnFallbackSky();
	SpawnWaterIfMissing();
	SpawnWorldContent();
	Super::StartPlay();
}

void AAetherGameMode::SpawnWorldContent()
{
	UWorld* W = GetWorld();
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	if (!DB) return;

	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	if (!TActorIterator<ACreatureSpawner>(W))
	{
		for (const FAetherSpawnerDef& D : DB->SpawnerDefs)
		{
			if (ACreatureSpawner* S = W->SpawnActor<ACreatureSpawner>(ACreatureSpawner::StaticClass(), D.Location, FRotator::ZeroRotator, P))
			{
				S->Biome = D.Biome;
				S->Radius = D.Radius;
				S->MaxAlive = D.MaxAlive;
			}
		}
	}
	if (!TActorIterator<AAetherShrine>(W))
	{
		for (const FVector& L : DB->ShrineLocations)
		{
			W->SpawnActor<AAetherShrine>(AAetherShrine::StaticClass(), L, FRotator::ZeroRotator, P);
		}
	}
	if (!TActorIterator<AWorldScatter>(W))
	{
		W->SpawnActor<AWorldScatter>(AWorldScatter::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, P);
	}
}

void AAetherGameMode::SpawnWaterIfMissing()
{
	UWorld* W = GetWorld();
	for (TActorIterator<AActor> It(W); It; ++It)
	{
		if (It->ActorHasTag(TEXT("AetherWater")) || It->GetClass()->GetName().StartsWith(TEXT("WaterBody"))) return;
	}
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
	if (!Plane) return;
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AStaticMeshActor* Water = W->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), FVector(0, 0, DB ? DB->SeaLevelZ : 0.f), FRotator::ZeroRotator, P);
	if (!Water) return;
	UStaticMeshComponent* SM = Water->GetStaticMeshComponent();
	SM->SetMobility(EComponentMobility::Movable);
	SM->SetStaticMesh(Plane);
	SM->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SM->SetCastShadow(false);
	Water->SetActorScale3D(FVector(14000.f, 14000.f, 1.f));
	if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Aetherwild/Materials/M_Water.M_Water"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		SM->SetMaterial(0, M);
	}
	Water->Tags.Add(TEXT("AetherWater"));
}

void AAetherGameMode::SpawnFallbackSky()
{
	UWorld* W = GetWorld();
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	if (!TActorIterator<ADirectionalLight>(W))
	{
		if (ADirectionalLight* Sun = W->SpawnActor<ADirectionalLight>(ADirectionalLight::StaticClass(), FVector(0, 0, 50000.f), FRotator(-40.f, -35.f, 0.f), P))
		{
			UDirectionalLightComponent* L = Cast<UDirectionalLightComponent>(Sun->GetLightComponent());
			L->SetMobility(EComponentMobility::Movable);
			L->SetIntensity(10.f);
			L->SetAtmosphereSunLight(true);
			L->SetAtmosphereSunLightIndex(0);
			L->SetDynamicShadowCascades(4);
			Sun->Tags.Add(TEXT("Sun"));
		}
		if (ADirectionalLight* Moon = W->SpawnActor<ADirectionalLight>(ADirectionalLight::StaticClass(), FVector(0, 0, 50000.f), FRotator(40.f, 145.f, 0.f), P))
		{
			UDirectionalLightComponent* L = Cast<UDirectionalLightComponent>(Moon->GetLightComponent());
			L->SetMobility(EComponentMobility::Movable);
			L->SetIntensity(0.4f);
			L->SetLightColor(FLinearColor(0.55f, 0.65f, 1.f));
			L->SetAtmosphereSunLight(true);
			L->SetAtmosphereSunLightIndex(1);
			Moon->Tags.Add(TEXT("Moon"));
		}
	}
	if (!TActorIterator<ASkyAtmosphere>(W))
	{
		W->SpawnActor<ASkyAtmosphere>(ASkyAtmosphere::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, P);
	}
	if (!TActorIterator<AVolumetricCloud>(W))
	{
		W->SpawnActor<AVolumetricCloud>(AVolumetricCloud::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, P);
	}
	if (!TActorIterator<ASkyLight>(W))
	{
		ASkyLight* Sky = W->SpawnActorDeferred<ASkyLight>(ASkyLight::StaticClass(), FTransform::Identity);
		if (Sky)
		{
			Sky->GetLightComponent()->SetMobility(EComponentMobility::Movable);
			Sky->GetLightComponent()->bRealTimeCapture = true;
			Sky->FinishSpawning(FTransform::Identity);
		}
	}
	if (!TActorIterator<AExponentialHeightFog>(W))
	{
		if (AExponentialHeightFog* Fog = W->SpawnActor<AExponentialHeightFog>(AExponentialHeightFog::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, P))
		{
			Fog->GetComponent()->SetFogDensity(0.015f);
			Fog->GetComponent()->SetVolumetricFog(true);
		}
	}
}
