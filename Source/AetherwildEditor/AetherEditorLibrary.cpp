#include "AetherEditorLibrary.h"

#include "Editor.h"
#include "Engine/World.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeProxy.h"
#include "Misc/FileHelper.h"
#include "Modules/ModuleManager.h"

bool UAetherEditorLibrary::ImportLandscapeFromHeightmap(const FString& HeightmapPath, FVector Location, FVector Scale,
	int32 QuadsPerSection, int32 SectionsPerComponent, int32 ComponentsPerSide)
{
	UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
	if (!World)
	{
		UE_LOG(LogTemp, Error, TEXT("Aetherwild : aucun monde d'editeur ouvert"));
		return false;
	}

	// --- lecture du PNG 16 bits en niveaux de gris
	TArray<uint8> FileData;
	if (!FFileHelper::LoadFileToArray(FileData, *HeightmapPath))
	{
		UE_LOG(LogTemp, Error, TEXT("Aetherwild : heightmap introuvable : %s"), *HeightmapPath);
		return false;
	}
	IImageWrapperModule& IWM = FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
	TSharedPtr<IImageWrapper> Png = IWM.CreateImageWrapper(EImageFormat::PNG);
	TArray64<uint8> Raw;
	if (!Png.IsValid() || !Png->SetCompressed(FileData.GetData(), FileData.Num()) || !Png->GetRaw(ERGBFormat::Gray, 16, Raw))
	{
		UE_LOG(LogTemp, Error, TEXT("Aetherwild : PNG 16 bits illisible"));
		return false;
	}
	const int32 Size = (int32)Png->GetWidth();
	const int32 SizeQuads = ComponentsPerSide * SectionsPerComponent * QuadsPerSection;
	if (Size != SizeQuads + 1 || (int32)Png->GetHeight() != Size)
	{
		UE_LOG(LogTemp, Error, TEXT("Aetherwild : taille %dx%d incompatible (attendu %d)"), Size, (int32)Png->GetHeight(), SizeQuads + 1);
		return false;
	}
	TArray<uint16> Heights;
	Heights.SetNumUninitialized(Size * Size);
	FMemory::Memcpy(Heights.GetData(), Raw.GetData(), Heights.Num() * sizeof(uint16));

	// --- creation du Landscape (meme chemin que l'outil "Import from File" de l'editeur)
	TMap<FGuid, TArray<uint16>> HeightDataPerLayer;
	HeightDataPerLayer.Add(FGuid(), MoveTemp(Heights));
	TMap<FGuid, TArray<FLandscapeImportLayerInfo>> MaterialLayersPerLayer;
	MaterialLayersPerLayer.Add(FGuid(), TArray<FLandscapeImportLayerInfo>());

	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ALandscape* Landscape = World->SpawnActor<ALandscape>(Location, FRotator::ZeroRotator, SP);
	if (!Landscape) return false;
	Landscape->SetActorRelativeScale3D(Scale);
	Landscape->Import(FGuid::NewGuid(), 0, 0, SizeQuads, SizeQuads, SectionsPerComponent, QuadsPerSection,
		HeightDataPerLayer, *HeightmapPath, MaterialLayersPerLayer, ELandscapeImportAlphamapType::Additive);
	Landscape->SetActorLabel(TEXT("Aether_Terrain"));

	if (ULandscapeInfo* Info = Landscape->GetLandscapeInfo())
	{
		Info->UpdateLayerInfoMap(Landscape);
	}
	Landscape->RegisterAllComponents();
	World->MarkPackageDirty();
	UE_LOG(LogTemp, Log, TEXT("Aetherwild : terrain %dx%d importe"), Size, Size);
	return true;
}
