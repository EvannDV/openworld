// AETHERWILD - Controles (Enhanced Input cree en C++ : aucun asset a configurer).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "AetherPlayerController.generated.h"

class UInputAction;
class UInputMappingContext;
struct FInputActionValue;
class AAetherPlayerCharacter;
class ACreature;
class AAetherHUD;

UCLASS()
class AETHERWILD_API AAetherPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AAetherPlayerController();

protected:
	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;

private:
	UInputAction* MakeAction(const TCHAR* Name, bool bAxis2D = false, bool bAxis1D = false);
	AAetherPlayerCharacter* Tamer() const;
	ACreature* RiddenCreature() const;
	AAetherHUD* Hud() const;
	bool UIBlocking() const;

	void OnMove(const FInputActionValue& V);
	void OnLook(const FInputActionValue& V);
	void OnJump();
	void OnJumpReleased();
	void OnJumpHeld();
	void OnDescend(const FInputActionValue& V);
	void OnSprintOn();
	void OnSprintOff();
	void OnAimOn();
	void OnAimOff();
	void OnPrimary();
	void OnAbility1();
	void OnAbility2();
	void OnAbility3();
	void OnAbility4();
	void OnUltimate();
	void OnCompanion();
	void OnWheel(const FInputActionValue& V);
	void OnCapsule();
	void OnMount();
	void OnInteract();
	void OnPotion();
	void OnTarget();
	void OnSneak();
	void OnBox();
	void OnHelp();
	void OnSave();
	void OnLoad();
	void OnUp();
	void OnDown();
	void OnLeft();
	void OnRight();
	void OnConfirm();
	void OnRelease();

	UPROPERTY() TObjectPtr<UInputMappingContext> Context;
	UPROPERTY() TMap<FName, TObjectPtr<UInputAction>> Actions;
};
