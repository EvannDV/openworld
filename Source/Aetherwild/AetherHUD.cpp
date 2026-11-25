#include "AetherHUD.h"

#include "AetherPlayerCharacter.h"
#include "AetherWorldSubsystem.h"
#include "Creature.h"
#include "CreatureCollectionComponent.h"
#include "CreatureDatabase.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"

namespace
{
	const FLinearColor GPanelText(0.92f, 0.94f, 0.97f);
	const FLinearColor GDim(0.6f, 0.65f, 0.7f);
	const FLinearColor GAccent(0.45f, 0.9f, 1.f);

	AAetherHUD* FindHUD(UWorld* World)
	{
		APlayerController* PC = World ? UGameplayStatics::GetPlayerController(World, 0) : nullptr;
		return PC ? Cast<AAetherHUD>(PC->GetHUD()) : nullptr;
	}
}

void AAetherHUD::PushFloatingText(UWorld* World, const FVector& Location, const FString& Text, const FLinearColor& Color)
{
	if (AAetherHUD* H = FindHUD(World))
	{
		H->Floats.Add({ Location, Text, Color, 0.f });
		if (H->Floats.Num() > 40) H->Floats.RemoveAt(0);
	}
}

void AAetherHUD::PushMessage(UWorld* World, const FString& Text, const FLinearColor& Color)
{
	if (AAetherHUD* H = FindHUD(World))
	{
		H->Messages.Add({ Text, Color, 0.f });
		if (H->Messages.Num() > 7) H->Messages.RemoveAt(0);
	}
}

AAetherPlayerCharacter* AAetherHUD::GetTamer() const
{
	APawn* Pawn = PlayerOwner ? PlayerOwner->GetPawn() : nullptr;
	if (AAetherPlayerCharacter* P = Cast<AAetherPlayerCharacter>(Pawn)) return P;
	if (ACreature* C = Cast<ACreature>(Pawn)) return C->GetRider();
	return nullptr;
}

// ---------------------------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------------------------

void AAetherHUD::Txt(const FString& Str, float X, float Y, const FLinearColor& Col, float Scale, UFont* Font)
{
	if (!Font) Font = GEngine->GetMediumFont();
	DrawText(Str, FLinearColor(0.f, 0.f, 0.f, 0.85f * Col.A), X + S(1.5f), Y + S(1.5f), Font, Scale * UIScale);
	DrawText(Str, Col, X, Y, Font, Scale * UIScale);
}

void AAetherHUD::TxtCentered(const FString& Str, float CX, float Y, const FLinearColor& Col, float Scale, UFont* Font)
{
	if (!Font) Font = GEngine->GetMediumFont();
	float W = 0.f, H = 0.f;
	GetTextSize(Str, W, H, Font, Scale * UIScale);
	Txt(Str, CX - W * 0.5f, Y, Col, Scale, Font);
}

void AAetherHUD::Panel(float X, float Y, float W, float H, float Alpha)
{
	DrawRect(FLinearColor(0.015f, 0.02f, 0.035f, Alpha), X, Y, W, H);
	DrawRect(FLinearColor(0.45f, 0.9f, 1.f, Alpha * 0.35f), X, Y, W, S(2.f));
}

void AAetherHUD::Bar(float X, float Y, float W, float H, float Frac, const FLinearColor& Col)
{
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.6f), X, Y, W, H);
	DrawRect(Col, X, Y, W * FMath::Clamp(Frac, 0.f, 1.f), H);
}

FLinearColor AAetherHUD::HPColor(float Frac) const
{
	if (Frac > 0.5f) return FLinearColor(0.25f, 0.9f, 0.35f);
	if (Frac > 0.2f) return FLinearColor(1.f, 0.8f, 0.15f);
	return FLinearColor(1.f, 0.25f, 0.2f);
}

// ---------------------------------------------------------------------------------------------

void AAetherHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas) return;
	UIScale = FMath::Max(0.6f, Canvas->ClipY / 1080.f);
	const float Dt = GetWorld()->GetDeltaSeconds();
	AAetherPlayerCharacter* P = GetTamer();
	if (!P) return;

	if (P->IsDowned())
	{
		DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.6f), 0, 0, Canvas->ClipX, Canvas->ClipY);
		TxtCentered(TEXT("Tu t'es evanoui..."), Canvas->ClipX * 0.5f, Canvas->ClipY * 0.45f, FLinearColor(1.f, 0.5f, 0.5f), 2.f, GEngine->GetLargeFont());
		return;
	}

	DrawNameplates(P);
	DrawFloats(Dt);
	DrawStatus(P);
	DrawParty(P);
	DrawAbilities(P);
	DrawItems(P);
	DrawTarget(P);
	DrawPrompts(P);
	DrawMessages(Dt);

	if (P->IsAiming() || P->IsRiding())
	{
		const float CX = Canvas->ClipX * 0.5f, CY = Canvas->ClipY * 0.5f;
		const FLinearColor C = P->GetHoveredCreature() ? FLinearColor(1.f, 0.85f, 0.3f) : FLinearColor(1.f, 1.f, 1.f, 0.8f);
		DrawRect(C, CX - S(10), CY - S(1), S(7), S(2));
		DrawRect(C, CX + S(3), CY - S(1), S(7), S(2));
		DrawRect(C, CX - S(1), CY - S(10), S(2), S(7));
		DrawRect(C, CX - S(1), CY + S(3), S(2), S(7));
	}

	if (P->NeedsStarter()) DrawStarter(P);
	if (bBoxOpen) DrawBox(P);
	if (bShowHelp) DrawHelp();
}

void AAetherHUD::DrawStatus(AAetherPlayerCharacter* P)
{
	const UAetherWorldSubsystem* WS = UAetherWorldSubsystem::Get(this);
	const UCreatureCollectionComponent* Col = P->GetCollection();
	const float X = S(24), Y = S(22), W = S(330);
	Panel(X, Y, W, S(92));
	Txt(FString::Printf(TEXT("Dresseur  niv. %d"), P->GetTamerLevel()), X + S(12), Y + S(8), GAccent, 1.f);
	Bar(X + S(12), Y + S(38), W - S(24), S(10), P->GetHP() / P->GetMaxHP(), HPColor(P->GetHP() / P->GetMaxHP()));
	FString Info = FString::Printf(TEXT("%d pieces"), Col->Coins);
	if (WS) Info = FString::Printf(TEXT("%s   %s   %s   |  %s"), *WS->GetClockString(), *Aether::PhaseName(WS->GetPhase()), *Aether::WeatherName(WS->Weather), *Info);
	Txt(Info, X + S(12), Y + S(58), GPanelText, 0.85f);
}

void AAetherHUD::DrawParty(AAetherPlayerCharacter* P)
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	UCreatureCollectionComponent* Col = P->GetCollection();
	if (!DB || !Col) return;
	const float X = S(24);
	float Y = S(132);
	const float W = S(300), H = S(50);
	const int32 Active = Col->GetActiveIndex();
	Txt(TEXT("POCHE  (molette : choisir, G : sortir/rentrer)"), X, Y - S(4), GDim, 0.7f, GEngine->GetSmallFont());
	Y += S(16);
	for (int32 i = 0; i < Col->Party.Num(); ++i)
	{
		const FCreatureInstance& I = Col->Party[i];
		const FSpeciesDef* Sp = DB->FindSpecies(I.SpeciesId);
		if (!Sp) continue;
		const FAetherStats St = Aether::ComputeStats(*Sp, I);
		const float HP = I.CurrentHP < 0.f ? St.MaxHP : I.CurrentHP;
		const bool bSel = i == Col->SelectedSlot;
		Panel(X, Y, W, H, bSel ? 0.75f : 0.45f);
		if (bSel) DrawRect(GAccent, X, Y, S(4), H);
		DrawRect(Aether::ElementColor(Sp->Element1), X + S(10), Y + S(10), S(8), S(8));
		if (Sp->Element2 != EAetherElement::Neutral) DrawRect(Aether::ElementColor(Sp->Element2), X + S(10), Y + S(20), S(8), S(8));
		Txt(FString::Printf(TEXT("%s%s  niv.%d"), *Aether::DisplayNameOf(I, Sp), I.bPrismatic ? TEXT(" *") : TEXT(""), I.Level),
			X + S(26), Y + S(4), Aether::RarityColor(Sp->Rarity), 0.85f);
		if (i == Active) Txt(TEXT("DEHORS"), X + W - S(70), Y + S(5), FLinearColor(0.5f, 1.f, 0.6f), 0.65f, GEngine->GetSmallFont());
		if (HP <= 0.f) Txt(TEXT("K.O."), X + W - S(70), Y + S(5), FLinearColor(1.f, 0.3f, 0.3f), 0.65f, GEngine->GetSmallFont());
		Bar(X + S(26), Y + S(33), W - S(40), S(7), HP / St.MaxHP, HPColor(HP / St.MaxHP));
		Y += H + S(6);
	}
}

void AAetherHUD::DrawAbilities(AAetherPlayerCharacter* P)
{
	ACreature* C = P->IsRiding() ? P->GetMount() : P->GetActiveCompanion();
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	if (!C || !DB) return;
	const TArray<FName>& Abs = C->GetData().Abilities;
	const float BW = S(150), BH = S(58), Gap = S(8);
	const float Total = 5 * BW + 4 * Gap;
	float X = (Canvas->ClipX - Total) * 0.5f;
	const float Y = Canvas->ClipY - BH - S(28);

	// fiche compagnon au-dessus
	const FSpeciesDef& Sp = C->GetSpecies();
	Panel(X, Y - S(50), Total, S(42), 0.5f);
	Txt(FString::Printf(TEXT("%s  niv.%d  -  %s%s"), *C->GetDisplayName(), C->GetData().Level, *Aether::ElementName(Sp.Element1),
		Sp.Element2 != EAetherElement::Neutral ? *(TEXT("/") + Aether::ElementName(Sp.Element2)) : TEXT("")), X + S(10), Y - S(46), GPanelText, 0.8f);
	Bar(X + S(10), Y - S(20), Total * 0.5f, S(8), C->GetHPFraction(), HPColor(C->GetHPFraction()));
	Txt(FString::Printf(TEXT("%d / %d PV"), FMath::RoundToInt(C->GetHP()), FMath::RoundToInt(C->GetStats().MaxHP)), X + Total * 0.5f + S(20), Y - S(28), GDim, 0.7f, GEngine->GetSmallFont());
	const int32 XPNeed = Aether::XPForNextLevel(C->GetData().Level);
	Bar(X + S(10), Y - S(10), Total * 0.5f, S(3), (float)C->GetData().XP / XPNeed, FLinearColor(0.4f, 0.6f, 1.f));
	if (C->Status != EAetherStatus::None) Txt(Aether::StatusName(C->Status), X + Total - S(130), Y - S(46), FLinearColor(0.85f, 0.55f, 1.f), 0.8f);

	for (int32 i = 0; i < 4; ++i)
	{
		Panel(X, Y, BW, BH, 0.6f);
		if (Abs.IsValidIndex(i))
		{
			if (const FAbilityDef* A = DB->FindAbility(Abs[i]))
			{
				DrawRect(Aether::ElementColor(A->Element), X, Y + BH - S(4), BW, S(4));
				Txt(FString::Printf(TEXT("%d"), i + 1), X + S(6), Y + S(4), GAccent, 0.8f);
				Txt(A->DisplayName, X + S(24), Y + S(4), GPanelText, 0.72f);
				Txt(FString::Printf(TEXT("%s  P%d"), *Aether::ElementName(A->Element), FMath::RoundToInt(A->Power)), X + S(24), Y + S(28), GDim, 0.62f, GEngine->GetSmallFont());
				const float CD = C->GetCooldownFraction(Abs[i]);
				if (CD > 0.f) DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.6f), X, Y, BW * CD, BH - S(4));
			}
		}
		X += BW + Gap;
	}
	// coup special
	Panel(X, Y, BW, BH, 0.6f);
	const FAbilityDef* U = DB->FindAbility(Sp.Ultimate);
	const bool bReady = C->Resonance >= 100.f;
	Txt(TEXT("R"), X + S(6), Y + S(4), bReady ? FLinearColor(1.f, 0.8f, 0.2f) : GDim, 0.8f);
	Txt(U ? U->DisplayName : TEXT("-"), X + S(24), Y + S(4), bReady ? FLinearColor(1.f, 0.85f, 0.3f) : GDim, 0.72f);
	Bar(X + S(8), Y + BH - S(14), BW - S(16), S(7), C->Resonance / 100.f, bReady ? FLinearColor(1.f, 0.75f, 0.1f) : FLinearColor(0.6f, 0.45f, 0.2f));
}

void AAetherHUD::DrawItems(AAetherPlayerCharacter* P)
{
	const UCreatureCollectionComponent* Col = P->GetCollection();
	const float W = S(250), H = S(118);
	const float X = Canvas->ClipX - W - S(24), Y = Canvas->ClipY - H - S(28);
	Panel(X, Y, W, H);
	Txt(TEXT("CAPSULES  (T)"), X + S(10), Y + S(6), GDim, 0.7f, GEngine->GetSmallFont());
	for (int32 i = 0; i < 3; ++i)
	{
		const ECapsuleTier T = (ECapsuleTier)i;
		const bool bSel = Col->SelectedCapsule == T;
		const float Ry = Y + S(24) + i * S(24);
		if (bSel) DrawRect(FLinearColor(1.f, 1.f, 1.f, 0.08f), X + S(4), Ry, W - S(8), S(22));
		DrawRect(Aether::CapsuleColor(T), X + S(12), Ry + S(6), S(10), S(10));
		Txt(FString::Printf(TEXT("%s  x%d"), *Aether::CapsuleName(T), Col->GetCapsuleCount(T)), X + S(30), Ry + S(1), bSel ? FLinearColor::White : GDim, 0.72f);
	}
	Txt(FString::Printf(TEXT("Potions (H) x%d"), Col->Potions), X + S(12), Y + H - S(24), FLinearColor(0.5f, 1.f, 0.6f), 0.72f);
}

void AAetherHUD::DrawTarget(AAetherPlayerCharacter* P)
{
	ACreature* T = Cast<ACreature>(P->GetAimTarget());
	if (!T) return;
	const FSpeciesDef& Sp = T->GetSpecies();
	const float W = S(460), H = S(118);
	const float X = (Canvas->ClipX - W) * 0.5f, Y = S(22);
	Panel(X, Y, W, H, 0.65f);
	DrawRect(Aether::RarityColor(Sp.Rarity), X, Y, W, S(3));
	Txt(FString::Printf(TEXT("%s%s  niv.%d"), *T->GetDisplayName(), T->GetData().bPrismatic ? TEXT("  * PRISMATIQUE *") : TEXT(""), T->GetData().Level),
		X + S(12), Y + S(8), Aether::RarityColor(Sp.Rarity), 1.f);
	FString Elem = Aether::ElementName(Sp.Element1);
	if (Sp.Element2 != EAetherElement::Neutral) Elem += TEXT(" / ") + Aether::ElementName(Sp.Element2);
	Txt(FString::Printf(TEXT("%s  -  %s%s"), *Aether::RarityName(Sp.Rarity), *Elem,
		P->GetCollection()->Caught.Contains(Sp.Id) ? TEXT("  - deja capture") : TEXT("")), X + S(12), Y + S(38), GDim, 0.75f);
	Bar(X + S(12), Y + S(62), W - S(24), S(9), T->GetHPFraction(), HPColor(T->GetHPFraction()));
	if (T->Status != EAetherStatus::None) Txt(Aether::StatusName(T->Status), X + W - S(110), Y + S(38), FLinearColor(0.85f, 0.55f, 1.f), 0.75f);

	FString Reason;
	const float Chance = P->GetCaptureChancePreview(Reason);
	if (Chance > 0.f)
	{
		const FLinearColor C = Chance > 0.5f ? FLinearColor(0.4f, 1.f, 0.5f) : (Chance > 0.2f ? FLinearColor(1.f, 0.85f, 0.3f) : FLinearColor(1.f, 0.5f, 0.4f));
		Txt(FString::Printf(TEXT("Chance de capture (%s) : %d%%"), *Aether::CapsuleName(P->GetCollection()->SelectedCapsule), FMath::RoundToInt(Chance * 100.f)),
			X + S(12), Y + S(82), C, 0.8f);
	}
	else if (!Reason.IsEmpty())
	{
		Txt(Reason, X + S(12), Y + S(82), FLinearColor(1.f, 0.55f, 0.35f), 0.7f);
	}
}

void AAetherHUD::DrawNameplates(AAetherPlayerCharacter* P)
{
	const FVector Eye = P->GetActorLocation();
	for (TActorIterator<ACreature> It(GetWorld()); It; ++It)
	{
		ACreature* C = *It;
		if (C->IsHidden() || C->GetMode() == ECreatureMode::Ridden) continue;
		const float D = FVector::Dist(C->GetActorLocation(), Eye);
		if (D > 3500.f) continue;
		const float HH = C->GetSimpleCollisionHalfHeight();
		const FVector Sc = Project(C->GetActorLocation() + FVector(0, 0, HH + 45.f));
		if (Sc.Z <= 0.f) continue;
		const float Alpha = FMath::Clamp(1.f - (D - 2500.f) / 1000.f, 0.f, 1.f);
		const FLinearColor NameCol = C->IsWild() ? Aether::RarityColor(C->GetSpecies().Rarity) : FLinearColor(0.5f, 1.f, 0.6f);
		const FString Label = FString::Printf(TEXT("%s  niv.%d"), *C->GetDisplayName(), C->GetData().Level);
		TxtCentered(Label, Sc.X, Sc.Y - S(26), FLinearColor(NameCol.R, NameCol.G, NameCol.B, Alpha), 0.7f, GEngine->GetSmallFont());
		const float BW = S(80);
		DrawRect(FLinearColor(0, 0, 0, 0.5f * Alpha), Sc.X - BW * 0.5f, Sc.Y - S(6), BW, S(5));
		const FLinearColor HC = HPColor(C->GetHPFraction());
		DrawRect(FLinearColor(HC.R, HC.G, HC.B, Alpha), Sc.X - BW * 0.5f, Sc.Y - S(6), BW * C->GetHPFraction(), S(5));
	}
}

void AAetherHUD::DrawFloats(float Dt)
{
	for (int32 i = Floats.Num() - 1; i >= 0; --i)
	{
		FFloatText& F = Floats[i];
		F.Age += Dt;
		if (F.Age > 1.6f) { Floats.RemoveAt(i); continue; }
		const FVector Sc = Project(F.Location + FVector(0, 0, F.Age * 70.f));
		if (Sc.Z <= 0.f) continue;
		const float A = FMath::Clamp(1.6f - F.Age, 0.f, 1.f);
		TxtCentered(F.Text, Sc.X, Sc.Y, FLinearColor(F.Color.R, F.Color.G, F.Color.B, A), 1.f);
	}
}

void AAetherHUD::DrawMessages(float Dt)
{
	float Y = Canvas->ClipY - S(330);
	const float X = S(24);
	for (int32 i = Messages.Num() - 1; i >= 0; --i)
	{
		Messages[i].Age += Dt;
		if (Messages[i].Age > 7.f) Messages.RemoveAt(i);
	}
	for (const FMessage& M : Messages)
	{
		const float A = FMath::Clamp(7.f - M.Age, 0.f, 1.f);
		Txt(M.Text, X, Y, FLinearColor(M.Color.R, M.Color.G, M.Color.B, A), 0.78f);
		Y += S(26);
	}
}

void AAetherHUD::DrawPrompts(AAetherPlayerCharacter* P)
{
	FString Prompt;
	if (P->IsNearShrine()) Prompt = TEXT("F : se reposer au Sanctuaire");
	else if (ACreature* C = P->GetActiveCompanion())
	{
		if (!P->IsRiding() && C->CanBeRidden() && FVector::Dist(C->GetActorLocation(), P->GetActorLocation()) < C->GetBodyRadius() + 600.f)
		{
			Prompt = FString::Printf(TEXT("E : chevaucher %s"), *C->GetDisplayName());
		}
	}
	if (!Prompt.IsEmpty()) TxtCentered(Prompt, Canvas->ClipX * 0.5f, Canvas->ClipY * 0.62f, FLinearColor::White, 0.9f);
	Txt(TEXT("F1 : aide    B : Sanctuaire / Bestiaire"), Canvas->ClipX - S(330), S(22), GDim, 0.65f, GEngine->GetSmallFont());
}

void AAetherHUD::DrawStarter(AAetherPlayerCharacter* P)
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	if (!DB) return;
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.55f), 0, 0, Canvas->ClipX, Canvas->ClipY);
	TxtCentered(TEXT("Choisis ton premier compagnon"), Canvas->ClipX * 0.5f, S(180), FLinearColor(1.f, 0.9f, 0.5f), 1.6f, GEngine->GetLargeFont());
	const int32 N = DB->StarterSpecies.Num();
	const float W = S(420), H = S(300), Gap = S(30);
	float X = (Canvas->ClipX - (N * W + (N - 1) * Gap)) * 0.5f;
	const float Y = S(300);
	for (int32 i = 0; i < N; ++i)
	{
		const FSpeciesDef* Sp = DB->FindSpecies(DB->StarterSpecies[i]);
		if (!Sp) continue;
		Panel(X, Y, W, H, 0.8f);
		DrawRect(Aether::ElementColor(Sp->Element1), X, Y, W, S(6));
		Txt(FString::Printf(TEXT("[%d]  %s"), i + 1, *Sp->DisplayName), X + S(16), Y + S(20), FLinearColor::White, 1.2f);
		Txt(Aether::ElementName(Sp->Element1), X + S(16), Y + S(62), Aether::ElementColor(Sp->Element1), 0.9f);
		// description sur plusieurs lignes
		TArray<FString> Words;
		Sp->Description.ParseIntoArray(Words, TEXT(" "));
		FString Line;
		float Ly = Y + S(100);
		for (const FString& Wd : Words)
		{
			if (Line.Len() + Wd.Len() > 38) { Txt(Line, X + S(16), Ly, GPanelText, 0.75f); Ly += S(24); Line.Reset(); }
			Line += Wd + TEXT(" ");
		}
		Txt(Line, X + S(16), Ly, GPanelText, 0.75f);
		X += W + Gap;
	}
}

void AAetherHUD::DrawCreatureDetails(const FCreatureInstance& Inst, float X, float Y, float W)
{
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	const FSpeciesDef* Sp = DB ? DB->FindSpecies(Inst.SpeciesId) : nullptr;
	if (!Sp) return;
	const FAetherStats St = Aether::ComputeStats(*Sp, Inst);
	Txt(FString::Printf(TEXT("%s%s  niv.%d"), *Aether::DisplayNameOf(Inst, Sp), Inst.bPrismatic ? TEXT(" (prismatique)") : TEXT(""), Inst.Level),
		X, Y, Aether::RarityColor(Sp->Rarity), 1.1f);
	FString Elem = Aether::ElementName(Sp->Element1);
	if (Sp->Element2 != EAetherElement::Neutral) Elem += TEXT(" / ") + Aether::ElementName(Sp->Element2);
	Txt(FString::Printf(TEXT("%s  -  %s"), *Aether::RarityName(Sp->Rarity), *Elem), X, Y + S(36), GDim, 0.8f);
	float Ly = Y + S(70);
	const float HP = Inst.CurrentHP < 0.f ? St.MaxHP : Inst.CurrentHP;
	Txt(FString::Printf(TEXT("PV %d/%d   ATT %d   DEF %d   ESP %d   VIT %d"), FMath::RoundToInt(HP), FMath::RoundToInt(St.MaxHP),
		FMath::RoundToInt(St.Attack), FMath::RoundToInt(St.Defense), FMath::RoundToInt(St.Spirit), FMath::RoundToInt(St.Speed)), X, Ly, GPanelText, 0.75f);
	Ly += S(30);
	Txt(TEXT("Capacites :"), X, Ly, GAccent, 0.75f);
	Ly += S(24);
	for (const FName& Id : Inst.Abilities)
	{
		if (const FAbilityDef* A = DB->FindAbility(Id))
		{
			DrawRect(Aether::ElementColor(A->Element), X, Ly + S(6), S(8), S(8));
			Txt(FString::Printf(TEXT("%s (P%d) - %s"), *A->DisplayName, FMath::RoundToInt(A->Power), *A->Description), X + S(16), Ly, GPanelText, 0.65f, GEngine->GetSmallFont());
			Ly += S(22);
		}
	}
	if (const FAbilityDef* U = DB->FindAbility(Sp->Ultimate))
	{
		Txt(FString::Printf(TEXT("Coup special : %s - %s"), *U->DisplayName, *U->Description), X, Ly + S(4), FLinearColor(1.f, 0.8f, 0.3f), 0.65f, GEngine->GetSmallFont());
		Ly += S(28);
	}
	FString Apt = FString::Join(Sp->Aptitudes, TEXT(", "));
	if (Sp->bRideable) Apt = TEXT("Monture") + FString(Apt.IsEmpty() ? TEXT("") : TEXT(", ")) + Apt;
	if (!Apt.IsEmpty()) { Txt(TEXT("Aptitudes : ") + Apt, X, Ly, FLinearColor(0.6f, 1.f, 0.7f), 0.7f); Ly += S(26); }
	if (!Sp->EvolvesTo.IsNone())
	{
		const FSpeciesDef* Ev = DB->FindSpecies(Sp->EvolvesTo);
		Txt(FString::Printf(TEXT("Metamorphose en %s au niveau %d"), Ev ? *Ev->DisplayName : *Sp->EvolvesTo.ToString(), Sp->EvolveLevel), X, Ly, FLinearColor(0.8f, 0.7f, 1.f), 0.7f);
		Ly += S(26);
	}
	TArray<FString> Words;
	Sp->Description.ParseIntoArray(Words, TEXT(" "));
	FString Line;
	const int32 MaxChars = FMath::Max(20, FMath::RoundToInt(W / S(9.5f)));
	for (const FString& Wd : Words)
	{
		if (Line.Len() + Wd.Len() > MaxChars) { Txt(Line, X, Ly, GDim, 0.7f); Ly += S(22); Line.Reset(); }
		Line += Wd + TEXT(" ");
	}
	Txt(Line, X, Ly, GDim, 0.7f);
}

void AAetherHUD::DrawBox(AAetherPlayerCharacter* P)
{
	UCreatureCollectionComponent* Col = P->GetCollection();
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	if (!Col || !DB) return;
	const float X = S(120), Y = S(90), W = Canvas->ClipX - S(240), H = Canvas->ClipY - S(180);
	Panel(X, Y, W, H, 0.9f);
	Txt(TEXT("SANCTUAIRE  -  Poche & stockage"), X + S(20), Y + S(14), GAccent, 1.2f);
	Txt(FString::Printf(TEXT("Bestiaire : %d vues  /  %d capturees  /  %d especes"), Col->Seen.Num(), Col->Caught.Num(), DB->GetSpeciesOrder().Num()),
		X + W - S(560), Y + S(20), FLinearColor(1.f, 0.85f, 0.4f), 0.8f);
	Txt(TEXT("Haut/Bas : choisir   Gauche/Droite : colonne   Entree : deplacer   Suppr : relacher   B : fermer"),
		X + S(20), Y + H - S(36), GDim, 0.7f);

	const float ColW = S(330), RowH = S(34);
	const TArray<FCreatureInstance>* Lists[2] = { &Col->Party, &Col->Box };
	const TCHAR* Titles[2] = { TEXT("POCHE (6 max)"), TEXT("STOCKAGE") };
	for (int32 c = 0; c < 2; ++c)
	{
		const float CX = X + S(20) + c * (ColW + S(20));
		float Ry = Y + S(64);
		Txt(Titles[c], CX, Ry, c == BoxColumn ? FLinearColor::White : GDim, 0.8f);
		Ry += S(30);
		const TArray<FCreatureInstance>& L = *Lists[c];
		const int32 MaxRows = FMath::Max(1, FMath::FloorToInt((H - S(180)) / RowH));
		const int32 First = (c == BoxColumn) ? FMath::Max(0, BoxIndex - MaxRows + 1) : 0;
		for (int32 i = First; i < L.Num() && i < First + MaxRows; ++i)
		{
			const FSpeciesDef* Sp = DB->FindSpecies(L[i].SpeciesId);
			const bool bSel = c == BoxColumn && i == BoxIndex;
			if (bSel) DrawRect(FLinearColor(0.45f, 0.9f, 1.f, 0.18f), CX - S(6), Ry - S(2), ColW, RowH - S(4));
			if (Sp) DrawRect(Aether::ElementColor(Sp->Element1), CX, Ry + S(8), S(10), S(10));
			Txt(FString::Printf(TEXT("%s  niv.%d"), *Aether::DisplayNameOf(L[i], Sp), L[i].Level), CX + S(18), Ry,
				Sp ? Aether::RarityColor(Sp->Rarity) : FLinearColor::White, 0.78f);
			Ry += RowH;
		}
		if (L.Num() == 0) Txt(TEXT("(vide)"), CX, Ry, GDim, 0.7f);
	}

	const TArray<FCreatureInstance>& Cur = *Lists[BoxColumn];
	if (Cur.IsValidIndex(BoxIndex))
	{
		DrawCreatureDetails(Cur[BoxIndex], X + S(20) + 2 * (ColW + S(20)), Y + S(64), W - 2 * (ColW + S(20)) - S(40));
	}

	// Bestiaire compact en bas
	float Bx = X + S(20);
	const float By = Y + H - S(80);
	for (const FName& Id : DB->GetSpeciesOrder())
	{
		const FSpeciesDef* Sp = DB->FindSpecies(Id);
		const bool bCaught = Col->Caught.Contains(Id), bSeen = Col->Seen.Contains(Id);
		const FString Name = bSeen ? Sp->DisplayName : TEXT("???");
		const FLinearColor C = bCaught ? Aether::RarityColor(Sp->Rarity) : (bSeen ? GDim : FLinearColor(0.35f, 0.35f, 0.4f));
		float TW = 0.f, TH = 0.f;
		GetTextSize(Name, TW, TH, GEngine->GetSmallFont(), 0.65f * UIScale);
		if (Bx + TW > X + W - S(20)) break;
		Txt(Name, Bx, By, C, 0.65f, GEngine->GetSmallFont());
		Bx += TW + S(18);
	}
}

void AAetherHUD::DrawHelp()
{
	const float W = S(760), H = S(640);
	const float X = (Canvas->ClipX - W) * 0.5f, Y = (Canvas->ClipY - H) * 0.5f;
	Panel(X, Y, W, H, 0.92f);
	Txt(TEXT("COMMANDES"), X + S(24), Y + S(18), GAccent, 1.2f);
	static const TCHAR* Lines[] = {
		TEXT("ZQSD / WASD ........ se deplacer          Souris ...... camera"),
		TEXT("Maj ................ sprint / galop        C ........... discretion"),
		TEXT("Espace ............. sauter / s'envoler    Ctrl ........ descendre (vol, nage)"),
		TEXT("Clic droit (maint.)  viser                 Clic gauche . lancer capsule / attaquer"),
		TEXT("1 2 3 4 ............ ordonner une capacite R ........... coup special (Resonance)"),
		TEXT("Tab ................ verrouiller une cible Molette ..... choisir dans la poche"),
		TEXT("G .................. sortir / rentrer le compagnon"),
		TEXT("E .................. chevaucher / descendre (creatures 'Monture')"),
		TEXT("T .................. changer de capsule    H ........... potion"),
		TEXT("F .................. Sanctuaire : soins + sauvegarde"),
		TEXT("B .................. Sanctuaire : stockage + Bestiaire"),
		TEXT("F5 / F9 ............ sauvegarder / charger"),
		TEXT(""),
		TEXT("CAPTURE : affaiblis la creature (PV bas), inflige-lui un statut (sommeil, gel...),"),
		TEXT("puis vise-la et lance une capsule. Certaines especes ont des conditions speciales :"),
		TEXT("heure, meteo, element de la derniere attaque, niveau de dresseur. La fiche de la"),
		TEXT("cible affiche la chance de capture ou la condition manquante."),
	};
	float Ly = Y + S(70);
	for (const TCHAR* L : Lines)
	{
		Txt(L, X + S(24), Ly, GPanelText, 0.75f);
		Ly += S(31);
	}
}

// ---------------------------------------------------------------------------------------------
// Navigation ecran Sanctuaire
// ---------------------------------------------------------------------------------------------

void AAetherHUD::ToggleBox()
{
	bBoxOpen = !bBoxOpen;
	BoxIndex = 0;
	BoxColumn = 0;
}

void AAetherHUD::BoxNavigate(int32 Delta)
{
	AAetherPlayerCharacter* P = GetTamer();
	if (!P) return;
	const int32 N = BoxColumn == 0 ? P->GetCollection()->Party.Num() : P->GetCollection()->Box.Num();
	BoxIndex = N > 0 ? (BoxIndex + Delta + N) % N : 0;
}

void AAetherHUD::BoxSwitchColumn()
{
	BoxColumn = 1 - BoxColumn;
	BoxIndex = 0;
}

void AAetherHUD::BoxConfirm()
{
	AAetherPlayerCharacter* P = GetTamer();
	if (!P) return;
	UCreatureCollectionComponent* Col = P->GetCollection();
	const bool bOk = BoxColumn == 0 ? Col->MovePartyToBox(BoxIndex) : Col->MoveBoxToParty(BoxIndex);
	if (!bOk) PushMessage(GetWorld(), BoxColumn == 0 ? TEXT("Il faut garder au moins une creature en poche") : TEXT("Poche pleine (6 max)"), FLinearColor(1.f, 0.6f, 0.4f));
	BoxNavigate(0);
}

void AAetherHUD::BoxRelease()
{
	AAetherPlayerCharacter* P = GetTamer();
	if (!P) return;
	if (P->GetCollection()->Release(BoxColumn == 1, BoxIndex))
	{
		PushMessage(GetWorld(), TEXT("La creature retourne a la nature."), FLinearColor(0.7f, 0.9f, 0.7f));
	}
	BoxNavigate(0);
}
