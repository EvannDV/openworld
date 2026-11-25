#include "CreatureDatabase.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Animation/AnimSequence.h"
#include "Engine/SkeletalMesh.h"
#include "AetherPlayerCharacter.h"
#include "Creature.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	TSharedPtr<FJsonObject> LoadJsonFile(const FString& Path)
	{
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *Path))
		{
			UE_LOG(LogAether, Error, TEXT("Fichier introuvable : %s"), *Path);
			return nullptr;
		}
		TSharedPtr<FJsonObject> Root;
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
		if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
		{
			UE_LOG(LogAether, Error, TEXT("JSON invalide : %s"), *Path);
			return nullptr;
		}
		return Root;
	}

	FString JStr(const TSharedPtr<FJsonObject>& O, const TCHAR* K, const FString& Def = FString())
	{
		FString S;
		return O.IsValid() && O->TryGetStringField(K, S) ? S : Def;
	}

	double JNum(const TSharedPtr<FJsonObject>& O, const TCHAR* K, double Def)
	{
		double D;
		return O.IsValid() && O->TryGetNumberField(K, D) ? D : Def;
	}

	bool JBool(const TSharedPtr<FJsonObject>& O, const TCHAR* K, bool Def)
	{
		bool B;
		return O.IsValid() && O->TryGetBoolField(K, B) ? B : Def;
	}

	template <typename TEnum>
	TEnum ParseEnum(const FString& S, TEnum Def)
	{
		if (S.IsEmpty()) return Def;
		const int64 V = StaticEnum<TEnum>()->GetValueByNameString(S);
		if (V == INDEX_NONE)
		{
			UE_LOG(LogAether, Warning, TEXT("Valeur inconnue '%s' pour %s"), *S, *StaticEnum<TEnum>()->GetName());
			return Def;
		}
		return (TEnum)V;
	}

	template <typename TEnum>
	TEnum JEnum(const TSharedPtr<FJsonObject>& O, const TCHAR* K, TEnum Def)
	{
		return ParseEnum<TEnum>(JStr(O, K), Def);
	}

	template <typename TEnum>
	TArray<TEnum> JEnumArray(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
	{
		TArray<TEnum> Out;
		const TArray<TSharedPtr<FJsonValue>>* Arr;
		if (O.IsValid() && O->TryGetArrayField(K, Arr))
		{
			for (const TSharedPtr<FJsonValue>& V : *Arr)
			{
				Out.Add(ParseEnum<TEnum>(V->AsString(), (TEnum)0));
			}
		}
		return Out;
	}

	TArray<FName> JNames(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
	{
		TArray<FName> Out;
		const TArray<TSharedPtr<FJsonValue>>* Arr;
		if (O.IsValid() && O->TryGetArrayField(K, Arr))
		{
			for (const TSharedPtr<FJsonValue>& V : *Arr) Out.Add(FName(*V->AsString()));
		}
		return Out;
	}

	FLinearColor JColor(const TSharedPtr<FJsonObject>& O, const TCHAR* K, const FLinearColor& Def)
	{
		const FString S = JStr(O, K);
		if (S.IsEmpty()) return Def;
		return FLinearColor(FColor::FromHex(S));
	}

	TMap<FName, FString> JStringMap(const TSharedPtr<FJsonObject>& O, const TCHAR* K)
	{
		TMap<FName, FString> Out;
		const TSharedPtr<FJsonObject>* Obj;
		if (O.IsValid() && O->TryGetObjectField(K, Obj))
		{
			for (const auto& Pair : (*Obj)->Values) Out.Add(FName(*Pair.Key), Pair.Value->AsString());
		}
		return Out;
	}

	FVector JVec(const TSharedPtr<FJsonValue>& V)
	{
		const TArray<TSharedPtr<FJsonValue>>& A = V->AsArray();
		return A.Num() >= 3 ? FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber()) : FVector::ZeroVector;
	}
}

FString UCreatureDatabase::DataDir()
{
	return FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Data"));
}

UCreatureDatabase* UCreatureDatabase::Get(const UObject* WorldContext)
{
	const UGameInstance* GI = UGameplayStatics::GetGameInstance(WorldContext);
	return GI ? GI->GetSubsystem<UCreatureDatabase>() : nullptr;
}

void UCreatureDatabase::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	LoadAbilities();
	LoadSpecies();
	LoadWorld();
	UE_LOG(LogAether, Log, TEXT("Base Aetherwild : %d especes, %d capacites, %d zones d'apparition, %d sanctuaires"),
		Species.Num(), Abilities.Num(), SpawnerDefs.Num(), ShrineLocations.Num());
}

void UCreatureDatabase::LoadAbilities()
{
	const TSharedPtr<FJsonObject> Root = LoadJsonFile(FPaths::Combine(DataDir(), TEXT("abilities.json")));
	const TArray<TSharedPtr<FJsonValue>>* Arr;
	if (!Root.IsValid() || !Root->TryGetArrayField(TEXT("abilities"), Arr)) return;

	for (const TSharedPtr<FJsonValue>& V : *Arr)
	{
		const TSharedPtr<FJsonObject> O = V->AsObject();
		FAbilityDef A;
		A.Id = FName(*JStr(O, TEXT("id")));
		A.DisplayName = JStr(O, TEXT("name"), A.Id.ToString());
		A.Description = JStr(O, TEXT("description"));
		A.Element = JEnum(O, TEXT("element"), EAetherElement::Neutral);
		A.Shape = JEnum(O, TEXT("shape"), EAbilityShape::Melee);
		A.Power = JNum(O, TEXT("power"), 40);
		A.Accuracy = JNum(O, TEXT("accuracy"), 0.95);
		A.Cooldown = JNum(O, TEXT("cooldown"), 2.0);
		A.Range = JNum(O, TEXT("range"), A.Shape == EAbilityShape::Projectile ? 1800 : 260);
		A.Radius = JNum(O, TEXT("radius"), 300);
		A.bSpecial = JBool(O, TEXT("special"), false);
		A.bUltimate = JBool(O, TEXT("ultimate"), false);
		A.Status = JEnum(O, TEXT("status"), EAetherStatus::None);
		A.StatusChance = JNum(O, TEXT("statusChance"), 0);
		A.StatusDuration = JNum(O, TEXT("statusDuration"), 4);
		A.BuffAmount = JNum(O, TEXT("buff"), 0);
		A.VfxScale = JNum(O, TEXT("vfxScale"), 1);
		Abilities.Add(A.Id, A);
	}
}

void UCreatureDatabase::LoadSpecies()
{
	const TSharedPtr<FJsonObject> Root = LoadJsonFile(FPaths::Combine(DataDir(), TEXT("species.json")));
	const TArray<TSharedPtr<FJsonValue>>* Arr;
	if (!Root.IsValid() || !Root->TryGetArrayField(TEXT("species"), Arr)) return;

	StarterSpecies = JNames(Root, TEXT("starters"));
	PlayerAssetFolder = JStr(Root, TEXT("playerAssetFolder"), PlayerAssetFolder);
	MeshYawOffset = JNum(Root, TEXT("meshYawOffset"), MeshYawOffset);
	const TSharedPtr<FJsonObject>* PlayerObj;
	if (Root->TryGetObjectField(TEXT("player"), PlayerObj))
	{
		PlayerBlueprintPath = JStr(*PlayerObj, TEXT("blueprint"));
		PlayerMeshPath = JStr(*PlayerObj, TEXT("mesh"));
		PlayerAnimBlueprintPath = JStr(*PlayerObj, TEXT("animBlueprint"));
		PlayerAnimPaths = JStringMap(*PlayerObj, TEXT("anims"));
		PlayerMeshYaw = JNum(*PlayerObj, TEXT("yaw"), MeshYawOffset);
		PlayerHeightCm = JNum(*PlayerObj, TEXT("heightCm"), 176.0);
	}

	for (const TSharedPtr<FJsonValue>& V : *Arr)
	{
		const TSharedPtr<FJsonObject> O = V->AsObject();
		FSpeciesDef S;
		S.Id = FName(*JStr(O, TEXT("id")));
		S.DisplayName = JStr(O, TEXT("name"), S.Id.ToString());
		S.Description = JStr(O, TEXT("description"));
		S.Element1 = JEnum(O, TEXT("element"), EAetherElement::Neutral);
		S.Element2 = JEnum(O, TEXT("element2"), EAetherElement::Neutral);
		S.Rarity = JEnum(O, TEXT("rarity"), EAetherRarity::Common);
		S.CatchRate = JNum(O, TEXT("catchRate"), 0.5);
		S.BaseXP = JNum(O, TEXT("baseXP"), 40);
		S.Biomes = JNames(O, TEXT("biomes"));
		S.SpawnPhase = JEnum(O, TEXT("spawnPhase"), EDayPhase::Any);
		S.SpawnWeathers = JEnumArray<EWeatherType>(O, TEXT("spawnWeathers"));
		S.MinLevel = JNum(O, TEXT("minLevel"), 2);
		S.MaxLevel = JNum(O, TEXT("maxLevel"), 8);
		S.SizeMeters = JNum(O, TEXT("size"), 1.0);
		S.Movement = JEnum(O, TEXT("movement"), EMovementStyle::Ground);
		S.bRideable = JBool(O, TEXT("rideable"), false);
		S.bEmitsLight = JBool(O, TEXT("emitsLight"), false);
		S.WalkSpeed = JNum(O, TEXT("walkSpeed"), 220);
		S.RunSpeed = JNum(O, TEXT("runSpeed"), 600);
		S.Temperament = JEnum(O, TEXT("temperament"), ETemperament::Docile);
		S.Ultimate = FName(*JStr(O, TEXT("ultimate")));
		S.EvolvesTo = FName(*JStr(O, TEXT("evolvesTo")));
		S.EvolveLevel = JNum(O, TEXT("evolveLevel"), 0);
		S.AssetFolder = JStr(O, TEXT("assetFolder"), FString::Printf(TEXT("/Game/Aetherwild/Creatures/%s"), *S.Id.ToString()));
		S.PrimaryColor = JColor(O, TEXT("color"), FLinearColor::Gray);
		S.AccentColor = JColor(O, TEXT("accent"), FLinearColor::White);

		const TSharedPtr<FJsonObject>* VisObj;
		if (O->TryGetObjectField(TEXT("visual"), VisObj))
		{
			S.BlueprintPath = JStr(*VisObj, TEXT("blueprint"));
			S.MeshPath = JStr(*VisObj, TEXT("mesh"));
			S.AnimBlueprintPath = JStr(*VisObj, TEXT("animBlueprint"));
			S.AnimPaths = JStringMap(*VisObj, TEXT("anims"));
			double Yaw;
			if ((*VisObj)->TryGetNumberField(TEXT("yaw"), Yaw)) { S.bOverrideYaw = true; S.MeshYaw = Yaw; }
			S.SaddleSocket = FName(*JStr(*VisObj, TEXT("saddleSocket"), TEXT("saddle")));
			S.bKeepMeshScale = JBool(*VisObj, TEXT("keepScale"), false);
		}

		const TArray<TSharedPtr<FJsonValue>>* Apt;
		if (O->TryGetArrayField(TEXT("aptitudes"), Apt))
		{
			for (const TSharedPtr<FJsonValue>& A : *Apt) S.Aptitudes.Add(A->AsString());
		}

		const TSharedPtr<FJsonObject>* StatsObj;
		if (O->TryGetObjectField(TEXT("stats"), StatsObj))
		{
			S.BaseStats.MaxHP = JNum(*StatsObj, TEXT("hp"), 50);
			S.BaseStats.Attack = JNum(*StatsObj, TEXT("atk"), 10);
			S.BaseStats.Defense = JNum(*StatsObj, TEXT("def"), 10);
			S.BaseStats.Spirit = JNum(*StatsObj, TEXT("spi"), 10);
			S.BaseStats.Speed = JNum(*StatsObj, TEXT("spd"), 10);
		}

		const TArray<TSharedPtr<FJsonValue>>* Learn;
		if (O->TryGetArrayField(TEXT("learnset"), Learn))
		{
			for (const TSharedPtr<FJsonValue>& L : *Learn)
			{
				const TArray<TSharedPtr<FJsonValue>>& Pair = L->AsArray();
				if (Pair.Num() == 2)
				{
					FLearnEntry E;
					E.Level = (int32)Pair[0]->AsNumber();
					E.Ability = FName(*Pair[1]->AsString());
					if (!Abilities.Contains(E.Ability))
					{
						UE_LOG(LogAether, Warning, TEXT("%s : capacite inconnue %s"), *S.Id.ToString(), *E.Ability.ToString());
					}
					S.Learnset.Add(E);
				}
			}
			S.Learnset.Sort([](const FLearnEntry& A, const FLearnEntry& B) { return A.Level < B.Level; });
		}

		const TSharedPtr<FJsonObject>* CapObj;
		if (O->TryGetObjectField(TEXT("capture"), CapObj))
		{
			S.Capture.Phase = JEnum(*CapObj, TEXT("phase"), EDayPhase::Any);
			S.Capture.Weathers = JEnumArray<EWeatherType>(*CapObj, TEXT("weathers"));
			S.Capture.WeakenedBy = JEnum(*CapObj, TEXT("weakenedBy"), EAetherElement::Neutral);
			S.Capture.MaxHealthFraction = JNum(*CapObj, TEXT("maxHealth"), 1.0);
			S.Capture.MinTamerLevel = JNum(*CapObj, TEXT("minTamerLevel"), 1);
			S.Capture.bRequiresStatus = JBool(*CapObj, TEXT("requiresStatus"), false);
			S.Capture.Hint = JStr(*CapObj, TEXT("hint"));
		}

		SpeciesOrder.Add(S.Id);
		Species.Add(S.Id, S);
	}
}

void UCreatureDatabase::LoadWorld()
{
	const TSharedPtr<FJsonObject> Root = LoadJsonFile(FPaths::Combine(DataDir(), TEXT("world.json")));
	if (Root.IsValid())
	{
		SeaLevelZ = JNum(Root, TEXT("seaLevelZ"), 0.0);
		const TArray<TSharedPtr<FJsonValue>>* Arr;
		if (Root->TryGetArrayField(TEXT("playerStart"), Arr) && Arr->Num() >= 3)
		{
			PlayerStart = FVector((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber(), (*Arr)[2]->AsNumber());
		}
		if (Root->TryGetArrayField(TEXT("volcano"), Arr) && Arr->Num() >= 2)
		{
			VolcanoXY = FVector2D((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber());
		}
		if (Root->TryGetArrayField(TEXT("shrines"), Arr))
		{
			for (const TSharedPtr<FJsonValue>& V : *Arr) ShrineLocations.Add(JVec(V));
		}
		if (Root->TryGetArrayField(TEXT("spawners"), Arr))
		{
			for (const TSharedPtr<FJsonValue>& V : *Arr)
			{
				const TSharedPtr<FJsonObject> O = V->AsObject();
				FAetherSpawnerDef D;
				D.Biome = FName(*JStr(O, TEXT("biome")));
				D.Radius = JNum(O, TEXT("radius"), 4000);
				D.MaxAlive = JNum(O, TEXT("maxAlive"), 4);
				const TArray<TSharedPtr<FJsonValue>>* Loc;
				if (O->TryGetArrayField(TEXT("location"), Loc) && Loc->Num() >= 3)
				{
					D.Location = FVector((*Loc)[0]->AsNumber(), (*Loc)[1]->AsNumber(), (*Loc)[2]->AsNumber());
				}
				SpawnerDefs.Add(D);
			}
		}
	}
	ScatterConfig = LoadJsonFile(FPaths::Combine(DataDir(), TEXT("scatter.json")));
}

FCreatureInstance UCreatureDatabase::MakeInstance(FName SpeciesId, int32 Level, FRandomStream& Rng) const
{
	FCreatureInstance I;
	I.Guid = FGuid::NewGuid();
	I.SpeciesId = SpeciesId;
	I.Level = FMath::Clamp(Level, 1, 100);
	I.Potential.MaxHP = Rng.FRandRange(0.9f, 1.15f);
	I.Potential.Attack = Rng.FRandRange(0.9f, 1.15f);
	I.Potential.Defense = Rng.FRandRange(0.9f, 1.15f);
	I.Potential.Spirit = Rng.FRandRange(0.9f, 1.15f);
	I.Potential.Speed = Rng.FRandRange(0.9f, 1.15f);
	I.bPrismatic = Rng.RandRange(1, 512) == 1;
	LearnAbilitiesForLevel(I, I.Level);
	I.CurrentHP = -1.f;
	return I;
}

TArray<FName> UCreatureDatabase::LearnAbilitiesForLevel(FCreatureInstance& Inst, int32 Level) const
{
	TArray<FName> Learned;
	const FSpeciesDef* S = FindSpecies(Inst.SpeciesId);
	if (!S) return Learned;
	for (const FLearnEntry& E : S->Learnset)
	{
		if (E.Level > Level || Inst.Abilities.Contains(E.Ability) || !Abilities.Contains(E.Ability)) continue;
		if (Inst.Abilities.Num() >= 4)
		{
			// Remplace la capacite la plus faible (hors soutien) par la nouvelle si elle est plus puissante.
			int32 Weakest = INDEX_NONE;
			float WeakestPower = TNumericLimits<float>::Max();
			for (int32 i = 0; i < Inst.Abilities.Num(); ++i)
			{
				const FAbilityDef* A = FindAbility(Inst.Abilities[i]);
				const float P = A ? A->Power : 0.f;
				if (P < WeakestPower) { WeakestPower = P; Weakest = i; }
			}
			const FAbilityDef* New = FindAbility(E.Ability);
			if (Weakest != INDEX_NONE && New && New->Power > WeakestPower)
			{
				Inst.Abilities[Weakest] = E.Ability;
				Learned.Add(E.Ability);
			}
		}
		else
		{
			Inst.Abilities.Add(E.Ability);
			Learned.Add(E.Ability);
		}
	}
	return Learned;
}

FName UCreatureDatabase::RollSpecies(FName Biome, EDayPhase Phase, EWeatherType Weather, FRandomStream& Rng, int32& OutLevel) const
{
	TArray<TPair<FName, int32>> Pool;
	int32 Total = 0;
	for (const FName& Id : SpeciesOrder)
	{
		const FSpeciesDef& S = Species[Id];
		if (!S.Biomes.Contains(Biome)) continue;
		if (S.SpawnPhase != EDayPhase::Any && S.SpawnPhase != Phase) continue;
		if (S.SpawnWeathers.Num() > 0 && !S.SpawnWeathers.Contains(Weather)) continue;
		const int32 W = Aether::RarityWeight(S.Rarity);
		Pool.Add({ Id, W });
		Total += W;
	}
	if (Total <= 0) return NAME_None;
	int32 Pick = Rng.RandRange(0, Total - 1);
	for (const TPair<FName, int32>& P : Pool)
	{
		if (Pick < P.Value)
		{
			const FSpeciesDef& S = Species[P.Key];
			OutLevel = Rng.RandRange(S.MinLevel, S.MaxLevel);
			return P.Key;
		}
		Pick -= P.Value;
	}
	return NAME_None;
}

void UCreatureDatabase::ResolveExplicitVisuals(FCreatureVisuals& V, const FString& MeshPath, const FString& AnimBPPath, const TMap<FName, FString>& AnimPaths)
{
	if (!MeshPath.IsEmpty())
	{
		if (USkeletalMesh* M = LoadObject<USkeletalMesh>(nullptr, *MeshPath)) V.Mesh = M;
		else UE_LOG(LogAether, Warning, TEXT("Mesh introuvable : %s"), *MeshPath);
	}
	if (!AnimBPPath.IsEmpty())
	{
		// accepte "/Game/X/ABP_Wolf" ou "/Game/X/ABP_Wolf.ABP_Wolf_C"
		FString ClassPath = AnimBPPath;
		if (!ClassPath.EndsWith(TEXT("_C")))
		{
			const FString Name = FPaths::GetBaseFilename(ClassPath.Contains(TEXT(".")) ? ClassPath.Left(ClassPath.Find(TEXT("."))) : ClassPath);
			ClassPath = (ClassPath.Contains(TEXT(".")) ? ClassPath.Left(ClassPath.Find(TEXT("."))) : ClassPath) + TEXT(".") + Name + TEXT("_C");
		}
		if (UClass* C = LoadClass<UAnimInstance>(nullptr, *ClassPath)) V.AnimClass = C;
		else UE_LOG(LogAether, Warning, TEXT("Animation Blueprint introuvable : %s"), *ClassPath);
	}
	for (const TPair<FName, FString>& P : AnimPaths)
	{
		if (UAnimSequence* Seq = LoadObject<UAnimSequence>(nullptr, *P.Value)) V.Anims.Add(P.Key, Seq);
		else UE_LOG(LogAether, Warning, TEXT("Animation introuvable : %s"), *P.Value);
	}
}

const FCreatureVisuals& UCreatureDatabase::GetVisuals(FName SpeciesId)
{
	const FSpeciesDef* S = FindSpecies(SpeciesId);
	if (S && (!S->MeshPath.IsEmpty() || !S->AnimBlueprintPath.IsEmpty() || S->AnimPaths.Num() > 0))
	{
		const FString Key = TEXT("species:") + S->Id.ToString();
		if (const FCreatureVisuals* Existing = VisualCache.Find(Key)) return *Existing;
		FCreatureVisuals V = GetVisualsForFolder(S->AssetFolder);   // base (modele procedural) ...
		ResolveExplicitVisuals(V, S->MeshPath, S->AnimBlueprintPath, S->AnimPaths);   // ... remplacee par les assets realistes
		V.bResolved = true;
		return VisualCache.Add(Key, V);
	}
	return GetVisualsForFolder(S ? S->AssetFolder : FString());
}

const FCreatureVisuals& UCreatureDatabase::GetPlayerVisuals()
{
	const FString Key = TEXT("player");
	if (const FCreatureVisuals* Existing = VisualCache.Find(Key)) return *Existing;
	FCreatureVisuals V = GetVisualsForFolder(PlayerAssetFolder);
	ResolveExplicitVisuals(V, PlayerMeshPath, PlayerAnimBlueprintPath, PlayerAnimPaths);
	V.bResolved = true;
	return VisualCache.Add(Key, V);
}

static UClass* LoadBlueprintClass(const FString& Path, UClass* Base)
{
	if (Path.IsEmpty()) return nullptr;
	FString ClassPath = Path;
	if (!ClassPath.EndsWith(TEXT("_C")))
	{
		const FString Pkg = ClassPath.Contains(TEXT(".")) ? ClassPath.Left(ClassPath.Find(TEXT("."))) : ClassPath;
		ClassPath = Pkg + TEXT(".") + FPaths::GetBaseFilename(Pkg) + TEXT("_C");
	}
	UClass* C = LoadClass<UObject>(nullptr, *ClassPath);
	if (!C || !C->IsChildOf(Base))
	{
		UE_LOG(LogAether, Warning, TEXT("Blueprint %s introuvable ou n'herite pas de %s"), *ClassPath, *Base->GetName());
		return nullptr;
	}
	return C;
}

UClass* UCreatureDatabase::GetCreatureClass(FName SpeciesId) const
{
	const FSpeciesDef* S = FindSpecies(SpeciesId);
	if (S && !S->BlueprintPath.IsEmpty())
	{
		if (UClass* C = LoadBlueprintClass(S->BlueprintPath, ACreature::StaticClass())) return C;
	}
	return ACreature::StaticClass();
}

UClass* UCreatureDatabase::GetPlayerPawnClass() const
{
	if (UClass* C = LoadBlueprintClass(PlayerBlueprintPath, AAetherPlayerCharacter::StaticClass())) return C;
	return AAetherPlayerCharacter::StaticClass();
}

const FCreatureVisuals& UCreatureDatabase::GetVisualsForFolder(const FString& Folder)
{
	FCreatureVisuals& V = VisualCache.FindOrAdd(Folder);
	if (V.bResolved || Folder.IsEmpty()) return V;
	V.bResolved = true;

	IAssetRegistry& AR = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
#if WITH_EDITOR
	AR.ScanPathsSynchronous({ Folder }, false);
#endif
	TArray<FAssetData> Assets;
	AR.GetAssetsByPath(FName(*Folder), Assets, true);

	static const TCHAR* Keys[] = { TEXT("Idle"), TEXT("Walk"), TEXT("Run"), TEXT("Attack"), TEXT("Fly"),
		TEXT("Swim"), TEXT("Throw"), TEXT("Ride") };
	for (const FAssetData& A : Assets)
	{
		if (A.AssetClassPath == USkeletalMesh::StaticClass()->GetClassPathName())
		{
			V.Mesh = Cast<USkeletalMesh>(A.GetAsset());
		}
		else if (A.AssetClassPath == UAnimSequence::StaticClass()->GetClassPathName())
		{
			const FString Name = A.AssetName.ToString();
			for (const TCHAR* K : Keys)
			{
				// "SK_Braisillon_Anim_Armature_Walk" ou "Walk" -> on teste la fin du nom
				if (Name.EndsWith(K) || Name.Contains(FString(TEXT("_")) + K + TEXT("_")))
				{
					if (UAnimSequence* Seq = Cast<UAnimSequence>(A.GetAsset()))
					{
						V.Anims.Add(FName(K), Seq);
					}
				}
			}
		}
	}
	if (!V.Mesh)
	{
		UE_LOG(LogAether, Warning, TEXT("Aucun SkeletalMesh dans %s (forme de secours utilisee). Lance Tools/Unreal/setup_aetherwild.py."), *Folder);
	}
	return V;
}
