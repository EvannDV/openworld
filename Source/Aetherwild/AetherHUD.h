// AETHERWILD - Interface en jeu (dessinee en Canvas : fonctionne sans aucun asset UMG).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "AetherHUD.generated.h"

class AAetherPlayerCharacter;
class ACreature;
class UFont;
struct FCreatureInstance;

UCLASS()
class AETHERWILD_API AAetherHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

	static void PushFloatingText(UWorld* World, const FVector& Location, const FString& Text, const FLinearColor& Color);
	static void PushMessage(UWorld* World, const FString& Text, const FLinearColor& Color);

	// Ecran "Sanctuaire" (stockage + bestiaire)
	void ToggleBox();
	bool IsBoxOpen() const { return bBoxOpen; }
	void BoxNavigate(int32 Delta);
	void BoxSwitchColumn();
	void BoxConfirm();
	void BoxRelease();
	void ToggleHelp() { bShowHelp = !bShowHelp; }

private:
	struct FFloatText { FVector Location; FString Text; FLinearColor Color; float Age = 0.f; };
	struct FMessage { FString Text; FLinearColor Color; float Age = 0.f; };

	AAetherPlayerCharacter* GetTamer() const;
	float S(float V) const { return V * UIScale; }
	void Txt(const FString& Str, float X, float Y, const FLinearColor& Col, float Scale = 1.f, UFont* Font = nullptr);
	void TxtCentered(const FString& Str, float CX, float Y, const FLinearColor& Col, float Scale = 1.f, UFont* Font = nullptr);
	void Panel(float X, float Y, float W, float H, float Alpha = 0.55f);
	void Bar(float X, float Y, float W, float H, float Frac, const FLinearColor& Col);
	FLinearColor HPColor(float Frac) const;

	void DrawStatus(AAetherPlayerCharacter* P);
	void DrawParty(AAetherPlayerCharacter* P);
	void DrawAbilities(AAetherPlayerCharacter* P);
	void DrawItems(AAetherPlayerCharacter* P);
	void DrawTarget(AAetherPlayerCharacter* P);
	void DrawNameplates(AAetherPlayerCharacter* P);
	void DrawFloats(float Dt);
	void DrawMessages(float Dt);
	void DrawPrompts(AAetherPlayerCharacter* P);
	void DrawStarter(AAetherPlayerCharacter* P);
	void DrawBox(AAetherPlayerCharacter* P);
	void DrawHelp();
	void DrawCreatureDetails(const FCreatureInstance& Inst, float X, float Y, float W);

	TArray<FFloatText> Floats;
	TArray<FMessage> Messages;
	float UIScale = 1.f;
	bool bShowHelp = false;
	bool bBoxOpen = false;
	int32 BoxColumn = 0;
	int32 BoxIndex = 0;
};
