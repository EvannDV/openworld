#include "CreatureCollectionComponent.h"

#include "AbilityEffects.h"
#include "AetherPlayerCharacter.h"
#include "Creature.h"
#include "CreatureDatabase.h"

#include "Components/CapsuleComponent.h"
#include "Engine/World.h"

UCreatureCollectionComponent::UCreatureCollectionComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	Capsules = { 10, 2, 0 };
}

AAetherPlayerCharacter* UCreatureCollectionComponent::GetTamer() const
{
	return Cast<AAetherPlayerCharacter>(GetOwner());
}

bool UCreatureCollectionComponent::AddCreature(const FCreatureInstance& Inst, bool& bOutToBox)
{
	Seen.Add(Inst.SpeciesId);
	Caught.Add(Inst.SpeciesId);
	if (Party.Num() < MaxParty)
	{
		Party.Add(Inst);
		bOutToBox = false;
	}
	else
	{
		Box.Add(Inst);
		bOutToBox = true;
	}
	return true;
}

int32 UCreatureCollectionComponent::GetActiveIndex() const
{
	if (!ActiveCompanion.IsValid()) return INDEX_NONE;
	return Party.IndexOfByPredicate([this](const FCreatureInstance& I) { return I.Guid == ActiveGuid; });
}

FCreatureInstance* UCreatureCollectionComponent::FindByGuid(const FGuid& Guid, bool* bOutInBox)
{
	for (FCreatureInstance& I : Party) if (I.Guid == Guid) { if (bOutInBox) *bOutInBox = false; return &I; }
	for (FCreatureInstance& I : Box) if (I.Guid == Guid) { if (bOutInBox) *bOutInBox = true; return &I; }
	return nullptr;
}

void UCreatureCollectionComponent::SyncFromCompanion(const FCreatureInstance& Data)
{
	if (FCreatureInstance* I = FindByGuid(Data.Guid)) *I = Data;
}

ACreature* UCreatureCollectionComponent::Deploy(int32 Slot)
{
	AAetherPlayerCharacter* T = GetTamer();
	if (!T || !Party.IsValidIndex(Slot)) return nullptr;
	FCreatureInstance& Inst = Party[Slot];
	if (Inst.CurrentHP == 0.f)
	{
		T->Notify(FString::Printf(TEXT("%s est K.O. - soigne-le au Sanctuaire ou avec une potion (H)"),
			*Aether::DisplayNameOf(Inst, UCreatureDatabase::Get(T)->FindSpecies(Inst.SpeciesId))), FLinearColor(1.f, 0.4f, 0.4f));
		return nullptr;
	}
	if (ActiveCompanion.IsValid()) Recall(true);

	// Point d'apparition : devant le joueur, au sol
	const FVector Fwd = T->GetActorForwardVector();
	FVector Loc = T->GetActorLocation() + Fwd * 350.f;
	FHitResult Hit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(AetherDeploy), false, T);
	if (GetWorld()->LineTraceSingleByObjectType(Hit, Loc + FVector(0, 0, 1500.f), Loc - FVector(0, 0, 5000.f), FCollisionObjectQueryParams(ECC_WorldStatic), Params))
	{
		Loc = Hit.ImpactPoint;
	}
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	ACreature* C = GetWorld()->SpawnActorDeferred<ACreature>(DB ? DB->GetCreatureClass(Inst.SpeciesId) : ACreature::StaticClass(), FTransform(Fwd.Rotation(), Loc + FVector(0, 0, 200.f)),
		nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
	if (!C) return nullptr;
	C->InitCreature(Inst, ECreatureMode::Companion, T);
	C->FinishSpawning(FTransform(Fwd.Rotation(), Loc + FVector(0, 0, C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 10.f)));
	ActiveCompanion = C;
	ActiveGuid = Inst.Guid;
	SelectedSlot = Slot;
	Seen.Add(Inst.SpeciesId);
	AAetherVfx::SpawnBurst(GetWorld(), C->GetActorLocation(), Aether::CapsuleColor(ECapsuleTier::Micro), 160.f, 0.5f);
	T->Notify(FString::Printf(TEXT("A toi, %s !"), *C->GetDisplayName()), FLinearColor(0.6f, 0.9f, 1.f));
	return C;
}

void UCreatureCollectionComponent::Recall(bool bInstant)
{
	ACreature* C = ActiveCompanion.Get();
	if (!C) return;
	if (AAetherPlayerCharacter* T = GetTamer())
	{
		if (T->IsRiding()) T->Dismount();
	}
	SyncFromCompanion(C->GetData());
	AAetherVfx::SpawnBurst(GetWorld(), C->GetActorLocation(), Aether::CapsuleColor(ECapsuleTier::Micro), 140.f, 0.4f);
	C->Destroy();
	ActiveCompanion = nullptr;
	ActiveGuid.Invalidate();
}

ACreature* UCreatureCollectionComponent::ToggleDeploy()
{
	if (ActiveCompanion.IsValid())
	{
		const int32 Active = GetActiveIndex();
		Recall();
		// si une autre creature est selectionnee, on fait l'echange directement
		if (Active != SelectedSlot && Party.IsValidIndex(SelectedSlot)) return Deploy(SelectedSlot);
		return nullptr;
	}
	return Deploy(SelectedSlot);
}

void UCreatureCollectionComponent::SelectNext(int32 Direction)
{
	if (Party.Num() == 0) return;
	SelectedSlot = (SelectedSlot + Direction + Party.Num()) % Party.Num();
}

bool UCreatureCollectionComponent::ConsumeCapsule(ECapsuleTier T)
{
	const int32 I = (int32)T;
	if (!Capsules.IsValidIndex(I) || Capsules[I] <= 0) return false;
	--Capsules[I];
	return true;
}

void UCreatureCollectionComponent::AddCapsules(ECapsuleTier T, int32 N)
{
	const int32 I = (int32)T;
	if (!Capsules.IsValidIndex(I)) Capsules.SetNumZeroed(3);
	Capsules[I] += N;
}

void UCreatureCollectionComponent::CycleCapsule()
{
	for (int32 i = 1; i <= 3; ++i)
	{
		const ECapsuleTier Next = (ECapsuleTier)(((int32)SelectedCapsule + i) % 3);
		if (GetCapsuleCount(Next) > 0 || i == 3)
		{
			SelectedCapsule = Next;
			return;
		}
	}
}

bool UCreatureCollectionComponent::UsePotion()
{
	if (Potions <= 0) return false;
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	if (ACreature* C = ActiveCompanion.Get())
	{
		if (C->GetHPFraction() >= 1.f) return false;
		C->Heal(C->GetStats().MaxHP * 0.5f);
		--Potions;
		AAetherVfx::SpawnBurst(GetWorld(), C->GetActorLocation(), FLinearColor(0.3f, 1.f, 0.4f), 150.f, 0.6f);
		return true;
	}
	if (Party.IsValidIndex(SelectedSlot) && DB)
	{
		FCreatureInstance& I = Party[SelectedSlot];
		if (const FSpeciesDef* S = DB->FindSpecies(I.SpeciesId))
		{
			const FAetherStats St = Aether::ComputeStats(*S, I);
			const float HP = I.CurrentHP < 0.f ? St.MaxHP : I.CurrentHP;
			if (HP >= St.MaxHP) return false;
			I.CurrentHP = FMath::Min(St.MaxHP, HP + St.MaxHP * 0.5f);
			--Potions;
			return true;
		}
	}
	return false;
}

void UCreatureCollectionComponent::HealAll()
{
	for (FCreatureInstance& I : Party) I.CurrentHP = -1.f;
	if (ACreature* C = ActiveCompanion.Get()) C->FullRestore();
}

void UCreatureCollectionComponent::AddTamerXP(int32 XP)
{
	const int32 Before = GetTamerLevel();
	TamerXP += XP;
	if (GetTamerLevel() > Before)
	{
		if (AAetherPlayerCharacter* T = GetTamer())
		{
			T->Notify(FString::Printf(TEXT("Niveau de dresseur %d ! (+3 micro-capsules)"), GetTamerLevel()), FLinearColor(1.f, 0.85f, 0.3f));
			AddCapsules(ECapsuleTier::Micro, 3);
			if (GetTamerLevel() % 3 == 0) AddCapsules(ECapsuleTier::Ultra, 2);
			if (GetTamerLevel() % 10 == 0) AddCapsules(ECapsuleTier::Prism, 1);
		}
	}
}

bool UCreatureCollectionComponent::MovePartyToBox(int32 PartyIndex)
{
	if (!Party.IsValidIndex(PartyIndex) || Party.Num() <= 1) return false;
	if (Party[PartyIndex].Guid == ActiveGuid) Recall(true);
	Box.Add(Party[PartyIndex]);
	Party.RemoveAt(PartyIndex);
	SelectedSlot = FMath::Clamp(SelectedSlot, 0, Party.Num() - 1);
	return true;
}

bool UCreatureCollectionComponent::MoveBoxToParty(int32 BoxIndex)
{
	if (!Box.IsValidIndex(BoxIndex) || Party.Num() >= MaxParty) return false;
	Party.Add(Box[BoxIndex]);
	Box.RemoveAt(BoxIndex);
	return true;
}

bool UCreatureCollectionComponent::Release(bool bFromBox, int32 Index)
{
	TArray<FCreatureInstance>& Arr = bFromBox ? Box : Party;
	if (!Arr.IsValidIndex(Index)) return false;
	if (!bFromBox && Party.Num() <= 1) return false;
	if (Arr[Index].Guid == ActiveGuid) Recall(true);
	Arr.RemoveAt(Index);
	SelectedSlot = FMath::Clamp(SelectedSlot, 0, FMath::Max(0, Party.Num() - 1));
	return true;
}

void UCreatureCollectionComponent::Evolve(const FGuid& Guid, FName NewSpecies)
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	FCreatureInstance* I = FindByGuid(Guid);
	if (!I || !DB || !DB->FindSpecies(NewSpecies)) return;
	const bool bWasActive = (Guid == ActiveGuid) && ActiveCompanion.IsValid();
	const int32 Slot = GetActiveIndex();
	if (bWasActive) Recall(true);
	I->SpeciesId = NewSpecies;
	I->CurrentHP = -1.f;
	FCreatureInstance Copy = *I;
	DB->LearnAbilitiesForLevel(Copy, Copy.Level);
	*I = Copy;
	Seen.Add(NewSpecies);
	Caught.Add(NewSpecies);
	if (bWasActive && Slot != INDEX_NONE) Deploy(Slot);
}
