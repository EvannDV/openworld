#include "WorldScatter.h"

#include "AetherTypes.h"
#include "CreatureDatabase.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Kismet/GameplayStatics.h"

AWorldScatter::AWorldScatter()
{
	PrimaryActorTick.bCanEverTick = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent->SetMobility(EComponentMobility::Static);
}

float AWorldScatter::ForestDensityAt(const FVector2D& XY)
{
	// Deux octaves de bruit de Perlin : grandes forets + clairieres.
	const float A = FMath::PerlinNoise2D(XY * 0.000035f);
	const float B = FMath::PerlinNoise2D(XY * 0.00013f + FVector2D(17.3f, 4.1f));
	return FMath::Clamp(0.5f + 0.75f * A + 0.25f * B, 0.f, 1.f);
}

void AWorldScatter::BeginPlay()
{
	Super::BeginPlay();
	if (const UCreatureDatabase* DB = UCreatureDatabase::Get(this))
	{
		SeaLevel = DB->SeaLevelZ;
		Volcano = DB->VolcanoXY;
	}
	LoadLayers();
}

void AWorldScatter::LoadLayers()
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	if (!DB || !DB->ScatterConfig.IsValid()) return;
	const TArray<TSharedPtr<FJsonValue>>* Arr;
	if (!DB->ScatterConfig->TryGetArrayField(TEXT("layers"), Arr)) return;

	auto Range = [](const TSharedPtr<FJsonObject>& O, const TCHAR* K, FVector2D Def)
	{
		const TArray<TSharedPtr<FJsonValue>>* R;
		if (O->TryGetArrayField(K, R) && R->Num() == 2) return FVector2D((*R)[0]->AsNumber(), (*R)[1]->AsNumber());
		return Def;
	};

	for (const TSharedPtr<FJsonValue>& V : *Arr)
	{
		const TSharedPtr<FJsonObject> O = V->AsObject();
		FScatterLayer L;
		O->TryGetStringField(TEXT("name"), L.Name);
		const TArray<TSharedPtr<FJsonValue>>* Meshes;
		if (O->TryGetArrayField(TEXT("meshes"), Meshes))
		{
			for (const TSharedPtr<FJsonValue>& M : *Meshes)
			{
				if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, *M->AsString(), nullptr, LOAD_NoWarn | LOAD_Quiet))
				{
					L.Meshes.Add(SM);
				}
			}
		}
		if (L.Meshes.Num() == 0)
		{
			UE_LOG(LogAether, Warning, TEXT("Scatter : couche '%s' ignoree (aucun mesh trouve)"), *L.Name);
			continue;
		}
		double D;
		if (O->TryGetNumberField(TEXT("density"), D)) L.DensityPerHectare = D;
		if (O->TryGetNumberField(TEXT("cellSize"), D)) L.CellSize = D * 100.0;
		if (O->TryGetNumberField(TEXT("viewCells"), D)) L.ViewCells = (int32)D;
		if (O->TryGetNumberField(TEXT("sink"), D)) L.Sink = D;
		L.Scale = Range(O, TEXT("scale"), L.Scale);
		L.Height = Range(O, TEXT("height"), L.Height);
		L.Slope = Range(O, TEXT("slope"), L.Slope);
		L.Forest = Range(O, TEXT("forest"), L.Forest);
		L.VolcanoDist = Range(O, TEXT("volcanoDist"), L.VolcanoDist);
		L.Cull = Range(O, TEXT("cull"), L.Cull);
		O->TryGetBoolField(TEXT("align"), L.bAlignToNormal);
		O->TryGetBoolField(TEXT("collision"), L.bCollision);
		O->TryGetBoolField(TEXT("shadows"), L.bShadows);
		Layers.Add(L);
	}
	CellComponents.SetNum(Layers.Num());
	Requested.SetNum(Layers.Num());
	UE_LOG(LogAether, Log, TEXT("Scatter : %d couches de vegetation"), Layers.Num());
}

void AWorldScatter::Tick(float Dt)
{
	Super::Tick(Dt);
	const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	if (!P || Layers.Num() == 0) return;

	RefreshTimer -= Dt;
	if (RefreshTimer <= 0.f)
	{
		RefreshTimer = 0.5f;
		const FVector PL = P->GetActorLocation();
		for (int32 Li = 0; Li < Layers.Num(); ++Li)
		{
			const FScatterLayer& L = Layers[Li];
			const FIntPoint Center(FMath::FloorToInt(PL.X / L.CellSize), FMath::FloorToInt(PL.Y / L.CellSize));
			TSet<FIntPoint> Wanted;
			for (int32 X = -L.ViewCells; X <= L.ViewCells; ++X)
			{
				for (int32 Y = -L.ViewCells; Y <= L.ViewCells; ++Y)
				{
					if (X * X + Y * Y <= (L.ViewCells + 0.5f) * (L.ViewCells + 0.5f)) Wanted.Add(Center + FIntPoint(X, Y));
				}
			}
			// liberation des cellules lointaines (avec marge d'une cellule pour eviter les va-et-vient)
			TArray<FIntPoint> ToRelease;
			for (const FIntPoint& C : Requested[Li])
			{
				const FIntPoint D = C - Center;
				if (FMath::Max(FMath::Abs(D.X), FMath::Abs(D.Y)) > L.ViewCells + 1) ToRelease.Add(C);
			}
			for (const FIntPoint& C : ToRelease) ReleaseCell(Li, C);

			// cellules a generer, les plus proches d'abord
			TArray<FIntPoint> NewCells;
			for (const FIntPoint& C : Wanted) if (!Requested[Li].Contains(C)) NewCells.Add(C);
			NewCells.Sort([&Center](const FIntPoint& A, const FIntPoint& B) { return (A - Center).SizeSquared() < (B - Center).SizeSquared(); });
			for (const FIntPoint& C : NewCells)
			{
				Requested[Li].Add(C);
				Queue.Add({ Li, C });
			}
		}
	}

	int32 Budget = TraceBudgetPerFrame;
	while (Budget > 0 && Queue.Num() > 0)
	{
		const FPendingCell Job = Queue[0];
		Queue.RemoveAt(0);
		if (!Requested[Job.Layer].Contains(Job.Cell)) continue;
		const FScatterLayer& L = Layers[Job.Layer];
		GenerateCell(Job.Layer, Job.Cell);
		Budget -= FMath::Max(50, FMath::RoundToInt(L.DensityPerHectare * (L.CellSize * L.CellSize) / 1e8f));
	}
}

void AWorldScatter::GenerateCell(int32 Li, const FIntPoint& Cell)
{
	const FScatterLayer& L = Layers[Li];
	const float AreaHa = (L.CellSize * L.CellSize) / 1e8f;   // cm^2 -> ha
	const int32 Count = FMath::RoundToInt(L.DensityPerHectare * AreaHa);
	if (Count <= 0) return;

	FRandomStream Rng(HashCombine(GetTypeHash(Cell), GetTypeHash(Li) * 7919u));
	TArray<TArray<FTransform>> PerMesh;
	PerMesh.SetNum(L.Meshes.Num());
	FCollisionQueryParams Params(SCENE_QUERY_STAT(AetherScatter), false, this);
	const float CosMax = FMath::Cos(FMath::DegreesToRadians(L.Slope.Y));
	const float CosMin = FMath::Cos(FMath::DegreesToRadians(L.Slope.X));

	for (int32 i = 0; i < Count; ++i)
	{
		const float X = (Cell.X + Rng.FRand()) * L.CellSize;
		const float Y = (Cell.Y + Rng.FRand()) * L.CellSize;
		const float Pick = Rng.FRand();
		const float Yaw = Rng.FRandRange(0.f, 360.f);
		const float S = Rng.FRandRange(L.Scale.X, L.Scale.Y);
		const float ForestRoll = Rng.FRand();

		const float Forest = ForestDensityAt(FVector2D(X, Y));
		// la densite forestiere module la probabilite plutot qu'un seuil dur -> lisieres naturelles
		const float ForestCenter = (L.Forest.X + L.Forest.Y) * 0.5f;
		const float ForestHalf = FMath::Max(0.05f, (L.Forest.Y - L.Forest.X) * 0.5f);
		const float ForestWeight = FMath::Clamp(1.f - FMath::Abs(Forest - ForestCenter) / ForestHalf, 0.f, 1.f);
		if (ForestRoll > FMath::Sqrt(ForestWeight)) continue;

		if (L.VolcanoDist.Y < 1e8f || L.VolcanoDist.X > 0.f)
		{
			const float VD = FVector2D::Distance(FVector2D(X, Y), Volcano) / 100.f;
			if (VD < L.VolcanoDist.X || VD > L.VolcanoDist.Y) continue;
		}

		FHitResult Hit;
		if (!GetWorld()->LineTraceSingleByObjectType(Hit, FVector(X, Y, 200000.f), FVector(X, Y, -200000.f), FCollisionObjectQueryParams(ECC_WorldStatic), Params))
		{
			continue;
		}
		const float Hm = (Hit.ImpactPoint.Z - SeaLevel) / 100.f;
		if (Hm < L.Height.X || Hm > L.Height.Y) continue;
		const float Nz = Hit.ImpactNormal.Z;
		if (Nz < CosMax || Nz > CosMin + 1e-3f) continue;

		FQuat Rot = FQuat(FRotator(0.f, Yaw, 0.f));
		if (L.bAlignToNormal)
		{
			Rot = FQuat::FindBetweenNormals(FVector::UpVector, Hit.ImpactNormal) * Rot;
		}
		const FVector Loc = Hit.ImpactPoint - Hit.ImpactNormal * L.Sink * S;
		const int32 MeshIdx = FMath::Min(L.Meshes.Num() - 1, FMath::FloorToInt(Pick * L.Meshes.Num()));
		PerMesh[MeshIdx].Add(FTransform(Rot, Loc, FVector(S)));
	}

	TArray<TObjectPtr<UHierarchicalInstancedStaticMeshComponent>>& Comps = CellComponents[Li].FindOrAdd(Cell);
	for (int32 m = 0; m < PerMesh.Num(); ++m)
	{
		if (PerMesh[m].Num() == 0) continue;
		UHierarchicalInstancedStaticMeshComponent* H = NewObject<UHierarchicalInstancedStaticMeshComponent>(this);
		H->SetMobility(EComponentMobility::Static);
		H->SetStaticMesh(L.Meshes[m]);
		H->SetCollisionEnabled(L.bCollision ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
		H->SetCastShadow(L.bShadows);
		H->bAffectDistanceFieldLighting = L.bShadows;
		if (L.Cull.Y > 0.f) H->SetCullDistances((int32)L.Cull.X, (int32)L.Cull.Y);
		H->SetupAttachment(RootComponent);
		H->RegisterComponent();
		H->AddInstances(PerMesh[m], false, true);
		Comps.Add(H);
	}
}

void AWorldScatter::ReleaseCell(int32 Li, const FIntPoint& Cell)
{
	Requested[Li].Remove(Cell);
	if (TArray<TObjectPtr<UHierarchicalInstancedStaticMeshComponent>>* Comps = CellComponents[Li].Find(Cell))
	{
		for (UHierarchicalInstancedStaticMeshComponent* H : *Comps)
		{
			if (H) H->DestroyComponent();
		}
		CellComponents[Li].Remove(Cell);
	}
}
