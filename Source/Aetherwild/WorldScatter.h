// AETHERWILD - Vegetation et rochers generes en continu autour du joueur (cellules streamees, instancing HISM).
// Les couches sont definies dans Content/Data/scatter.json : remplace les meshes par des assets
// Megascans/Fab (arbres Nanite, herbe) pour un rendu photorealiste, sans toucher au code.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WorldScatter.generated.h"

class UStaticMesh;
class UHierarchicalInstancedStaticMeshComponent;

USTRUCT()
struct FScatterLayer
{
	GENERATED_BODY()

	FString Name;
	UPROPERTY() TArray<TObjectPtr<UStaticMesh>> Meshes;
	float DensityPerHectare = 50.f;
	float CellSize = 25600.f;          // cm
	int32 ViewCells = 2;               // rayon en cellules
	FVector2D Scale = FVector2D(0.8f, 1.2f);
	FVector2D Height = FVector2D(0.5f, 2000.f);   // m
	FVector2D Slope = FVector2D(0.f, 35.f);       // degres
	FVector2D Forest = FVector2D(0.f, 1.f);       // densite forestiere 0..1
	FVector2D VolcanoDist = FVector2D(0.f, 1e9f); // m
	bool bAlignToNormal = false;
	bool bCollision = false;
	bool bShadows = true;
	FVector2D Cull = FVector2D(0.f, 0.f);         // cm
	float Sink = 0.f;                             // cm
};

UCLASS()
class AETHERWILD_API AWorldScatter : public AActor
{
	GENERATED_BODY()

public:
	AWorldScatter();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Traces maximum par image (budget de generation). */
	UPROPERTY(EditAnywhere, Category = "Aether") int32 TraceBudgetPerFrame = 1500;

	static float ForestDensityAt(const FVector2D& XY);

private:
	struct FPendingCell { int32 Layer; FIntPoint Cell; };

	void LoadLayers();
	void GenerateCell(int32 LayerIdx, const FIntPoint& Cell);
	void ReleaseCell(int32 LayerIdx, const FIntPoint& Cell);

	UPROPERTY() TArray<FScatterLayer> Layers;
	TArray<TMap<FIntPoint, TArray<TObjectPtr<UHierarchicalInstancedStaticMeshComponent>>>> CellComponents;
	TArray<TSet<FIntPoint>> Requested;
	TArray<FPendingCell> Queue;
	float SeaLevel = 0.f;
	FVector2D Volcano = FVector2D::ZeroVector;
	float RefreshTimer = 0.f;
};
