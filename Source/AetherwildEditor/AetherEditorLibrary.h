// AETHERWILD - Outils d'editeur appelables depuis Python (unreal.AetherEditorLibrary).
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AetherEditorLibrary.generated.h"

UCLASS()
class AETHERWILDEDITOR_API UAetherEditorLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Cree un Landscape dans le niveau ouvert a partir d'une heightmap PNG 16 bits (sans passer par l'interface).
	 * Python : unreal.AetherEditorLibrary.import_landscape_from_heightmap(path, location, scale, 63, 2, 32)
	 */
	UFUNCTION(BlueprintCallable, Category = "Aetherwild|Editor")
	static bool ImportLandscapeFromHeightmap(const FString& HeightmapPath, FVector Location, FVector Scale,
		int32 QuadsPerSection = 63, int32 SectionsPerComponent = 2, int32 ComponentsPerSide = 32);
};
