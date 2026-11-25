#include "CreatureSpawner.h"

#include "AetherWorldSubsystem.h"
#include "Creature.h"
#include "CreatureDatabase.h"

#include "Components/CapsuleComponent.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"

ACreatureSpawner::ACreatureSpawner()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 1.f;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Rng.GenerateNewSeed();
}

void ACreatureSpawner::Tick(float Dt)
{
	Super::Tick(Dt);
	Alive.RemoveAll([](const TWeakObjectPtr<ACreature>& C) { return !C.IsValid() || C->IsFainted(); });

	const APawn* Player = UGameplayStatics::GetPlayerPawn(this, 0);
	if (!Player) return;
	const FVector PL = Player->GetActorLocation();
	const float Dist = FVector::Dist2D(PL, GetActorLocation());

	// Trop loin : on libere les creatures (sauf en combat) pour garder de bonnes performances.
	if (Dist > ActivationDistance + Radius * 1.5f)
	{
		for (const TWeakObjectPtr<ACreature>& C : Alive)
		{
			if (C.IsValid() && !C->GetCombatTarget() && !C->IsBeingCaptured()) C->Destroy();
		}
		Alive.Reset();
		return;
	}
	if (Dist > ActivationDistance) return;

	Cooldown -= Dt;
	if (Alive.Num() < MaxAlive && Cooldown <= 0.f)
	{
		SpawnOne(PL);
		Cooldown = Alive.Num() < MaxAlive / 2 ? 2.f : RespawnDelay * Rng.FRandRange(0.6f, 1.4f);
	}
}

bool ACreatureSpawner::FindSpawnPoint(bool bWaterSpecies, bool bFlying, const FVector& PlayerLoc, FVector& Out) const
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	const float Sea = DB ? DB->SeaLevelZ : 0.f;
	for (int32 Try = 0; Try < 8; ++Try)
	{
		const FVector2D R = FMath::RandPointInCircle(Radius);
		const FVector P = GetActorLocation() + FVector(R.X, R.Y, 0.f);
		if (FVector::Dist2D(P, PlayerLoc) < 1800.f) continue;   // pas d'apparition sous le nez du joueur
		FHitResult Hit;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(AetherSpawn), false, this);
		const bool bHit = GetWorld()->LineTraceSingleByObjectType(Hit, FVector(P.X, P.Y, P.Z + 60000.f), FVector(P.X, P.Y, P.Z - 60000.f),
			FCollisionObjectQueryParams(ECC_WorldStatic), Params);
		const bool bWater = !bHit || Hit.ImpactPoint.Z < Sea - 150.f;
		if (bWaterSpecies != bWater && !bFlying) continue;
		if (bHit && !bWater && Hit.ImpactNormal.Z < 0.72f) continue;   // pente trop forte
		Out = bWater ? FVector(P.X, P.Y, Sea) : Hit.ImpactPoint;
		return true;
	}
	return false;
}

void ACreatureSpawner::SpawnOne(const FVector& PlayerLoc)
{
	UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	const UAetherWorldSubsystem* WS = UAetherWorldSubsystem::Get(this);
	if (!DB) return;
	int32 Level = 1;
	const FName Id = DB->RollSpecies(Biome, WS ? WS->GetPhase() : EDayPhase::Day, WS ? WS->Weather : EWeatherType::Clear, Rng, Level);
	const FSpeciesDef* S = DB->FindSpecies(Id);
	if (!S) return;

	// Une seule creature legendaire de chaque espece dans le monde.
	if (S->Rarity == EAetherRarity::Legendary)
	{
		for (TActorIterator<ACreature> It(GetWorld()); It; ++It)
		{
			if (It->GetSpecies().Id == Id) return;
		}
	}

	FVector Loc;
	if (!FindSpawnPoint(S->IsAquaticOnly(), S->CanFly(), PlayerLoc, Loc)) return;

	const FTransform Xf(FRotator(0.f, Rng.FRandRange(0.f, 360.f), 0.f), Loc + FVector(0, 0, 300.f));
	ACreature* C = GetWorld()->SpawnActorDeferred<ACreature>(DB->GetCreatureClass(Id), Xf, nullptr, nullptr,
		ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
	if (!C) return;
	C->InitCreature(DB->MakeInstance(Id, Level, Rng), ECreatureMode::Wild);
	C->HomeSpawner = this;
	const float HH = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	C->FinishSpawning(FTransform(Xf.GetRotation(), Loc + FVector(0, 0, HH + 20.f)));
	C->HomeLocation = Loc;
	Alive.Add(C);
}
