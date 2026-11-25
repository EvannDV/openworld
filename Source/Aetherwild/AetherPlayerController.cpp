#include "AetherPlayerController.h"

#include "AetherHUD.h"
#include "AetherPlayerCharacter.h"
#include "Creature.h"

#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Kismet/GameplayStatics.h"

AAetherPlayerController::AAetherPlayerController()
{
	static const TCHAR* Bools[] = {
		TEXT("Jump"), TEXT("Sprint"), TEXT("Aim"), TEXT("Primary"), TEXT("Ability1"), TEXT("Ability2"), TEXT("Ability3"),
		TEXT("Ability4"), TEXT("Ultimate"), TEXT("Companion"), TEXT("Capsule"), TEXT("Mount"), TEXT("Interact"), TEXT("Potion"),
		TEXT("Target"), TEXT("Sneak"), TEXT("Box"), TEXT("Help"), TEXT("Save"), TEXT("Load"), TEXT("Up"), TEXT("Down"),
		TEXT("Left"), TEXT("Right"), TEXT("Confirm"), TEXT("Release") };
	for (const TCHAR* N : Bools) MakeAction(N);
	MakeAction(TEXT("Move"), true);
	MakeAction(TEXT("Look"), true);
	MakeAction(TEXT("Wheel"), false, true);
	MakeAction(TEXT("Descend"), false, true);
}

UInputAction* AAetherPlayerController::MakeAction(const TCHAR* Name, bool bAxis2D, bool bAxis1D)
{
	UInputAction* A = CreateDefaultSubobject<UInputAction>(FName(FString(TEXT("IA_")) + Name));
	A->ValueType = bAxis2D ? EInputActionValueType::Axis2D : (bAxis1D ? EInputActionValueType::Axis1D : EInputActionValueType::Boolean);
	Actions.Add(FName(Name), A);
	return A;
}

void AAetherPlayerController::BeginPlay()
{
	Super::BeginPlay();

	Context = NewObject<UInputMappingContext>(this, TEXT("IMC_Aetherwild"));
	auto Map = [this](const TCHAR* Action, const FKey& Key) -> FEnhancedActionKeyMapping&
	{
		return Context->MapKey(Actions.FindChecked(FName(Action)), Key);
	};
	auto Swizzle = [this](FEnhancedActionKeyMapping& M)
	{
		M.Modifiers.Add(NewObject<UInputModifierSwizzleAxis>(Context));
	};
	auto Negate = [this](FEnhancedActionKeyMapping& M)
	{
		M.Modifiers.Add(NewObject<UInputModifierNegate>(Context));
	};

	// Deplacement : ZQSD (AZERTY) + WASD (QWERTY) + fleches + manette
	for (const FKey& K : { EKeys::W, EKeys::Z }) { FEnhancedActionKeyMapping& M = Map(TEXT("Move"), K); Swizzle(M); }
	{ FEnhancedActionKeyMapping& M = Map(TEXT("Move"), EKeys::S); Swizzle(M); Negate(M); }
	for (const FKey& K : { EKeys::A, EKeys::Q }) { FEnhancedActionKeyMapping& M = Map(TEXT("Move"), K); Negate(M); }
	Map(TEXT("Move"), EKeys::D);
	Map(TEXT("Move"), EKeys::Gamepad_Left2D);
	Map(TEXT("Look"), EKeys::Mouse2D);
	Map(TEXT("Look"), EKeys::Gamepad_Right2D);

	Map(TEXT("Jump"), EKeys::SpaceBar);
	Map(TEXT("Jump"), EKeys::Gamepad_FaceButton_Bottom);
	Map(TEXT("Descend"), EKeys::LeftControl);
	Map(TEXT("Descend"), EKeys::Gamepad_LeftShoulder);
	Map(TEXT("Sprint"), EKeys::LeftShift);
	Map(TEXT("Sprint"), EKeys::Gamepad_LeftThumbstick);
	Map(TEXT("Aim"), EKeys::RightMouseButton);
	Map(TEXT("Aim"), EKeys::Gamepad_LeftTriggerAxis);
	Map(TEXT("Primary"), EKeys::LeftMouseButton);
	Map(TEXT("Primary"), EKeys::Gamepad_RightTriggerAxis);
	Map(TEXT("Ability1"), EKeys::One);
	Map(TEXT("Ability2"), EKeys::Two);
	Map(TEXT("Ability3"), EKeys::Three);
	Map(TEXT("Ability4"), EKeys::Four);
	// clavier AZERTY : & é " ' sans Maj
	Map(TEXT("Ability1"), EKeys::Ampersand);
	Map(TEXT("Ability2"), EKeys::E_AccentAigu);
	Map(TEXT("Ability3"), EKeys::Quote);
	Map(TEXT("Ability4"), EKeys::Apostrophe);
	Map(TEXT("Ability1"), EKeys::Gamepad_FaceButton_Left);
	Map(TEXT("Ability2"), EKeys::Gamepad_FaceButton_Top);
	Map(TEXT("Ability3"), EKeys::Gamepad_FaceButton_Right);
	Map(TEXT("Ultimate"), EKeys::R);
	Map(TEXT("Ultimate"), EKeys::Gamepad_RightShoulder);
	Map(TEXT("Companion"), EKeys::G);   // G : identique en AZERTY et QWERTY (Q/A servent au deplacement)
	Map(TEXT("Companion"), EKeys::Gamepad_DPad_Up);
	Map(TEXT("Wheel"), EKeys::MouseWheelAxis);
	{ FEnhancedActionKeyMapping& M = Map(TEXT("Wheel"), EKeys::Gamepad_DPad_Right); (void)M; }
	{ FEnhancedActionKeyMapping& M = Map(TEXT("Wheel"), EKeys::Gamepad_DPad_Left); Negate(M); }
	Map(TEXT("Capsule"), EKeys::T);
	Map(TEXT("Capsule"), EKeys::Gamepad_DPad_Down);
	Map(TEXT("Mount"), EKeys::E);
	Map(TEXT("Mount"), EKeys::Gamepad_RightThumbstick);
	Map(TEXT("Interact"), EKeys::F);
	Map(TEXT("Interact"), EKeys::Gamepad_Special_Left);
	Map(TEXT("Potion"), EKeys::H);
	Map(TEXT("Target"), EKeys::Tab);
	Map(TEXT("Sneak"), EKeys::C);
	Map(TEXT("Box"), EKeys::B);
	Map(TEXT("Box"), EKeys::Gamepad_Special_Right);
	Map(TEXT("Help"), EKeys::F1);
	Map(TEXT("Save"), EKeys::F5);
	Map(TEXT("Load"), EKeys::F9);
	Map(TEXT("Up"), EKeys::Up);
	Map(TEXT("Down"), EKeys::Down);
	Map(TEXT("Left"), EKeys::Left);
	Map(TEXT("Right"), EKeys::Right);
	Map(TEXT("Confirm"), EKeys::Enter);
	Map(TEXT("Release"), EKeys::Delete);

	if (UEnhancedInputLocalPlayerSubsystem* Sub = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer()))
	{
		Sub->AddMappingContext(Context, 0);
	}
	SetInputMode(FInputModeGameOnly());
	bShowMouseCursor = false;
}

void AAetherPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(InputComponent);
	if (!EIC)
	{
		UE_LOG(LogTemp, Error, TEXT("Aetherwild : EnhancedInputComponent manquant (voir Config/DefaultInput.ini)"));
		return;
	}
	auto A = [this](const TCHAR* N) { return Actions.FindChecked(FName(N)).Get(); };
	EIC->BindAction(A(TEXT("Move")), ETriggerEvent::Triggered, this, &AAetherPlayerController::OnMove);
	EIC->BindAction(A(TEXT("Look")), ETriggerEvent::Triggered, this, &AAetherPlayerController::OnLook);
	EIC->BindAction(A(TEXT("Jump")), ETriggerEvent::Started, this, &AAetherPlayerController::OnJump);
	EIC->BindAction(A(TEXT("Jump")), ETriggerEvent::Completed, this, &AAetherPlayerController::OnJumpReleased);
	EIC->BindAction(A(TEXT("Jump")), ETriggerEvent::Triggered, this, &AAetherPlayerController::OnJumpHeld);
	EIC->BindAction(A(TEXT("Descend")), ETriggerEvent::Triggered, this, &AAetherPlayerController::OnDescend);
	EIC->BindAction(A(TEXT("Sprint")), ETriggerEvent::Started, this, &AAetherPlayerController::OnSprintOn);
	EIC->BindAction(A(TEXT("Sprint")), ETriggerEvent::Completed, this, &AAetherPlayerController::OnSprintOff);
	EIC->BindAction(A(TEXT("Aim")), ETriggerEvent::Started, this, &AAetherPlayerController::OnAimOn);
	EIC->BindAction(A(TEXT("Aim")), ETriggerEvent::Completed, this, &AAetherPlayerController::OnAimOff);
	EIC->BindAction(A(TEXT("Primary")), ETriggerEvent::Started, this, &AAetherPlayerController::OnPrimary);
	EIC->BindAction(A(TEXT("Ability1")), ETriggerEvent::Started, this, &AAetherPlayerController::OnAbility1);
	EIC->BindAction(A(TEXT("Ability2")), ETriggerEvent::Started, this, &AAetherPlayerController::OnAbility2);
	EIC->BindAction(A(TEXT("Ability3")), ETriggerEvent::Started, this, &AAetherPlayerController::OnAbility3);
	EIC->BindAction(A(TEXT("Ability4")), ETriggerEvent::Started, this, &AAetherPlayerController::OnAbility4);
	EIC->BindAction(A(TEXT("Ultimate")), ETriggerEvent::Started, this, &AAetherPlayerController::OnUltimate);
	EIC->BindAction(A(TEXT("Companion")), ETriggerEvent::Started, this, &AAetherPlayerController::OnCompanion);
	EIC->BindAction(A(TEXT("Wheel")), ETriggerEvent::Started, this, &AAetherPlayerController::OnWheel);
	EIC->BindAction(A(TEXT("Capsule")), ETriggerEvent::Started, this, &AAetherPlayerController::OnCapsule);
	EIC->BindAction(A(TEXT("Mount")), ETriggerEvent::Started, this, &AAetherPlayerController::OnMount);
	EIC->BindAction(A(TEXT("Interact")), ETriggerEvent::Started, this, &AAetherPlayerController::OnInteract);
	EIC->BindAction(A(TEXT("Potion")), ETriggerEvent::Started, this, &AAetherPlayerController::OnPotion);
	EIC->BindAction(A(TEXT("Target")), ETriggerEvent::Started, this, &AAetherPlayerController::OnTarget);
	EIC->BindAction(A(TEXT("Sneak")), ETriggerEvent::Started, this, &AAetherPlayerController::OnSneak);
	EIC->BindAction(A(TEXT("Box")), ETriggerEvent::Started, this, &AAetherPlayerController::OnBox);
	EIC->BindAction(A(TEXT("Help")), ETriggerEvent::Started, this, &AAetherPlayerController::OnHelp);
	EIC->BindAction(A(TEXT("Save")), ETriggerEvent::Started, this, &AAetherPlayerController::OnSave);
	EIC->BindAction(A(TEXT("Load")), ETriggerEvent::Started, this, &AAetherPlayerController::OnLoad);
	EIC->BindAction(A(TEXT("Up")), ETriggerEvent::Started, this, &AAetherPlayerController::OnUp);
	EIC->BindAction(A(TEXT("Down")), ETriggerEvent::Started, this, &AAetherPlayerController::OnDown);
	EIC->BindAction(A(TEXT("Left")), ETriggerEvent::Started, this, &AAetherPlayerController::OnLeft);
	EIC->BindAction(A(TEXT("Right")), ETriggerEvent::Started, this, &AAetherPlayerController::OnRight);
	EIC->BindAction(A(TEXT("Confirm")), ETriggerEvent::Started, this, &AAetherPlayerController::OnConfirm);
	EIC->BindAction(A(TEXT("Release")), ETriggerEvent::Started, this, &AAetherPlayerController::OnRelease);
}

AAetherPlayerCharacter* AAetherPlayerController::Tamer() const
{
	if (AAetherPlayerCharacter* P = Cast<AAetherPlayerCharacter>(GetPawn())) return P;
	if (ACreature* C = Cast<ACreature>(GetPawn())) return C->GetRider();
	return nullptr;
}

ACreature* AAetherPlayerController::RiddenCreature() const
{
	return Cast<ACreature>(GetPawn());
}

AAetherHUD* AAetherPlayerController::Hud() const
{
	return Cast<AAetherHUD>(GetHUD());
}

bool AAetherPlayerController::UIBlocking() const
{
	const AAetherHUD* H = Hud();
	return H && H->IsBoxOpen();
}

// ---------------------------------------------------------------------------------------------

void AAetherPlayerController::OnMove(const FInputActionValue& V)
{
	if (UIBlocking()) return;
	const FVector2D In = V.Get<FVector2D>();
	if (ACreature* C = RiddenCreature()) C->RiderMove(In);
	else if (AAetherPlayerCharacter* P = Tamer()) P->Move(In);
}

void AAetherPlayerController::OnLook(const FInputActionValue& V)
{
	if (UIBlocking()) return;
	const FVector2D In = V.Get<FVector2D>();
	AddYawInput(In.X);
	AddPitchInput(-In.Y);
}

void AAetherPlayerController::OnJump()
{
	if (UIBlocking()) return;
	if (ACreature* C = RiddenCreature()) { C->RiderJump(); C->RiderVertical(1.f); return; }
	if (ACharacter* Ch = Cast<ACharacter>(GetPawn())) Ch->Jump();
}

void AAetherPlayerController::OnJumpHeld()
{
	if (ACreature* C = RiddenCreature()) C->RiderVertical(1.f);
}

void AAetherPlayerController::OnJumpReleased()
{
	if (ACreature* C = RiddenCreature()) { C->RiderVertical(0.f); return; }
	if (ACharacter* Ch = Cast<ACharacter>(GetPawn())) Ch->StopJumping();
}

void AAetherPlayerController::OnDescend(const FInputActionValue& V)
{
	if (ACreature* C = RiddenCreature()) C->RiderVertical(-FMath::Abs(V.Get<float>()));
}

void AAetherPlayerController::OnSprintOn()
{
	if (ACreature* C = RiddenCreature()) C->RiderSprint(true);
	else if (AAetherPlayerCharacter* P = Tamer()) P->SetSprint(true);
}

void AAetherPlayerController::OnSprintOff()
{
	if (ACreature* C = RiddenCreature()) C->RiderSprint(false);
	else if (AAetherPlayerCharacter* P = Tamer()) P->SetSprint(false);
}

void AAetherPlayerController::OnAimOn() { if (AAetherPlayerCharacter* P = Tamer()) P->SetAiming(true); }
void AAetherPlayerController::OnAimOff() { if (AAetherPlayerCharacter* P = Tamer()) P->SetAiming(false); }
void AAetherPlayerController::OnPrimary() { if (!UIBlocking()) if (AAetherPlayerCharacter* P = Tamer()) P->PrimaryAction(); }

void AAetherPlayerController::OnAbility1()
{
	AAetherPlayerCharacter* P = Tamer();
	if (!P) return;
	if (P->NeedsStarter()) P->ChooseStarter(0); else P->CommandAbility(1);
}

void AAetherPlayerController::OnAbility2()
{
	AAetherPlayerCharacter* P = Tamer();
	if (!P) return;
	if (P->NeedsStarter()) P->ChooseStarter(1); else P->CommandAbility(2);
}

void AAetherPlayerController::OnAbility3()
{
	AAetherPlayerCharacter* P = Tamer();
	if (!P) return;
	if (P->NeedsStarter()) P->ChooseStarter(2); else P->CommandAbility(3);
}

void AAetherPlayerController::OnAbility4() { if (AAetherPlayerCharacter* P = Tamer()) P->CommandAbility(4); }
void AAetherPlayerController::OnUltimate() { if (AAetherPlayerCharacter* P = Tamer()) P->CommandUltimate(); }
void AAetherPlayerController::OnCompanion() { if (!UIBlocking()) if (AAetherPlayerCharacter* P = Tamer()) P->ToggleCompanion(); }

void AAetherPlayerController::OnWheel(const FInputActionValue& V)
{
	const float W = V.Get<float>();
	if (UIBlocking()) { if (AAetherHUD* H = Hud()) H->BoxNavigate(W > 0 ? -1 : 1); return; }
	if (AAetherPlayerCharacter* P = Tamer()) P->CycleParty(W > 0 ? -1 : 1);
}

void AAetherPlayerController::OnCapsule() { if (AAetherPlayerCharacter* P = Tamer()) P->CycleCapsule(); }
void AAetherPlayerController::OnMount() { if (!UIBlocking()) if (AAetherPlayerCharacter* P = Tamer()) P->ToggleMount(); }
void AAetherPlayerController::OnInteract() { if (AAetherPlayerCharacter* P = Tamer()) P->Interact(); }
void AAetherPlayerController::OnPotion() { if (AAetherPlayerCharacter* P = Tamer()) P->UsePotion(); }
void AAetherPlayerController::OnTarget() { if (AAetherPlayerCharacter* P = Tamer()) P->CycleTarget(); }
void AAetherPlayerController::OnSneak() { if (AAetherPlayerCharacter* P = Tamer()) P->ToggleSneak(); }
void AAetherPlayerController::OnBox() { if (AAetherHUD* H = Hud()) H->ToggleBox(); }
void AAetherPlayerController::OnHelp() { if (AAetherHUD* H = Hud()) H->ToggleHelp(); }

void AAetherPlayerController::OnSave()
{
	if (AAetherPlayerCharacter* P = Tamer())
	{
		P->SaveProgress();
		P->Notify(TEXT("Partie sauvegardee"), FLinearColor(0.6f, 1.f, 0.7f));
	}
}

void AAetherPlayerController::OnLoad()
{
	// Recharger le niveau relit la sauvegarde au demarrage.
	UGameplayStatics::OpenLevel(this, FName(*UGameplayStatics::GetCurrentLevelName(this)));
}

void AAetherPlayerController::OnUp() { if (AAetherHUD* H = Hud(); H && H->IsBoxOpen()) H->BoxNavigate(-1); }
void AAetherPlayerController::OnDown() { if (AAetherHUD* H = Hud(); H && H->IsBoxOpen()) H->BoxNavigate(1); }
void AAetherPlayerController::OnLeft() { if (AAetherHUD* H = Hud(); H && H->IsBoxOpen()) H->BoxSwitchColumn(); }
void AAetherPlayerController::OnRight() { if (AAetherHUD* H = Hud(); H && H->IsBoxOpen()) H->BoxSwitchColumn(); }
void AAetherPlayerController::OnConfirm() { if (AAetherHUD* H = Hud(); H && H->IsBoxOpen()) H->BoxConfirm(); }
void AAetherPlayerController::OnRelease() { if (AAetherHUD* H = Hud(); H && H->IsBoxOpen()) H->BoxRelease(); }
