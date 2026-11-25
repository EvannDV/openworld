#include "AetherTypes.h"

DEFINE_LOG_CATEGORY(LogAether);

namespace Aether
{
	// Table d'efficacite [attaquant][defenseur] (ordre de EAetherElement).
	//                              Neu   Fir   Wat   Nat   Sto   Sto   Fro   Sha   Lig
	static const float GChart[9][9] = {
		/* Neutral */ { 1.0f, 1.0f, 1.0f, 1.0f, 0.5f, 1.0f, 1.0f, 1.0f, 1.0f },
		/* Fire    */ { 1.0f, 0.5f, 0.5f, 2.0f, 0.5f, 1.0f, 2.0f, 1.0f, 1.0f },
		/* Water   */ { 1.0f, 2.0f, 0.5f, 0.5f, 2.0f, 1.0f, 0.5f, 1.0f, 1.0f },
		/* Nature  */ { 1.0f, 0.5f, 2.0f, 0.5f, 2.0f, 0.5f, 1.0f, 1.0f, 1.0f },
		/* Stone   */ { 1.0f, 2.0f, 1.0f, 0.5f, 1.0f, 2.0f, 2.0f, 1.0f, 1.0f },
		/* Storm   */ { 1.0f, 1.0f, 2.0f, 0.5f, 0.5f, 0.5f, 1.0f, 1.0f, 1.0f },
		/* Frost   */ { 1.0f, 0.5f, 0.5f, 2.0f, 1.0f, 2.0f, 0.5f, 1.0f, 1.0f },
		/* Shadow  */ { 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 0.5f, 2.0f },
		/* Light   */ { 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 2.0f, 0.5f },
	};

	float Effectiveness(EAetherElement Attack, EAetherElement Defender)
	{
		return GChart[(int32)Attack][(int32)Defender];
	}

	float EffectivenessVs(EAetherElement Attack, const FSpeciesDef& Defender)
	{
		float M = Effectiveness(Attack, Defender.Element1);
		if (Defender.Element2 != EAetherElement::Neutral && Defender.Element2 != Defender.Element1)
		{
			M *= Effectiveness(Attack, Defender.Element2);
		}
		return M;
	}

	FAetherStats ComputeStats(const FSpeciesDef& S, const FCreatureInstance& I)
	{
		const float L = (float)FMath::Max(1, I.Level);
		const float Grow = 1.f + L * 0.075f;
		FAetherStats R;
		R.MaxHP   = FMath::RoundToFloat(S.BaseStats.MaxHP * (1.f + L * 0.1f) * I.Potential.MaxHP + L * 2.f);
		R.Attack  = S.BaseStats.Attack  * Grow * I.Potential.Attack;
		R.Defense = S.BaseStats.Defense * Grow * I.Potential.Defense;
		R.Spirit  = S.BaseStats.Spirit  * Grow * I.Potential.Spirit;
		R.Speed   = S.BaseStats.Speed   * Grow * I.Potential.Speed;
		if (I.bPrismatic)
		{
			R.Attack *= 1.05f; R.Spirit *= 1.05f;
		}
		return R;
	}

	int32 XPForNextLevel(int32 Level)
	{
		return FMath::RoundToInt(12.f * FMath::Pow((float)FMath::Max(1, Level), 1.7f)) + 10;
	}

	int32 RarityWeight(EAetherRarity R)
	{
		switch (R)
		{
		case EAetherRarity::Common:    return 60;
		case EAetherRarity::Uncommon:  return 26;
		case EAetherRarity::Rare:      return 10;
		case EAetherRarity::Epic:      return 4;
		case EAetherRarity::Legendary: return 1;
		}
		return 1;
	}

	FString ElementName(EAetherElement E)
	{
		static const TCHAR* N[] = { TEXT("Neutre"), TEXT("Feu"), TEXT("Eau"), TEXT("Nature"), TEXT("Roche"),
			TEXT("Foudre"), TEXT("Givre"), TEXT("Ombre"), TEXT("Lumiere") };
		return N[(int32)E];
	}

	FLinearColor ElementColor(EAetherElement E)
	{
		switch (E)
		{
		case EAetherElement::Fire:   return FLinearColor(1.0f, 0.35f, 0.1f);
		case EAetherElement::Water:  return FLinearColor(0.15f, 0.5f, 1.0f);
		case EAetherElement::Nature: return FLinearColor(0.3f, 0.85f, 0.25f);
		case EAetherElement::Stone:  return FLinearColor(0.65f, 0.55f, 0.4f);
		case EAetherElement::Storm:  return FLinearColor(1.0f, 0.9f, 0.2f);
		case EAetherElement::Frost:  return FLinearColor(0.6f, 0.9f, 1.0f);
		case EAetherElement::Shadow: return FLinearColor(0.55f, 0.3f, 0.9f);
		case EAetherElement::Light:  return FLinearColor(1.0f, 0.95f, 0.7f);
		default:                     return FLinearColor(0.8f, 0.8f, 0.8f);
		}
	}

	FString RarityName(EAetherRarity R)
	{
		static const TCHAR* N[] = { TEXT("Commun"), TEXT("Peu commun"), TEXT("Rare"), TEXT("Epique"), TEXT("Legendaire") };
		return N[(int32)R];
	}

	FLinearColor RarityColor(EAetherRarity R)
	{
		switch (R)
		{
		case EAetherRarity::Common:    return FLinearColor(0.85f, 0.85f, 0.85f);
		case EAetherRarity::Uncommon:  return FLinearColor(0.35f, 0.95f, 0.4f);
		case EAetherRarity::Rare:      return FLinearColor(0.3f, 0.6f, 1.0f);
		case EAetherRarity::Epic:      return FLinearColor(0.75f, 0.35f, 1.0f);
		case EAetherRarity::Legendary: return FLinearColor(1.0f, 0.7f, 0.1f);
		}
		return FLinearColor::White;
	}

	FString StatusName(EAetherStatus S)
	{
		static const TCHAR* N[] = { TEXT(""), TEXT("Brulure"), TEXT("Trempe"), TEXT("Enracine"), TEXT("Etourdi"),
			TEXT("Gele"), TEXT("Aveugle"), TEXT("Endormi") };
		return N[(int32)S];
	}

	FString PhaseName(EDayPhase P)
	{
		static const TCHAR* N[] = { TEXT("Toute heure"), TEXT("Jour"), TEXT("Nuit"), TEXT("Aube/Crepuscule") };
		return N[(int32)P];
	}

	FString WeatherName(EWeatherType W)
	{
		static const TCHAR* N[] = { TEXT("Degage"), TEXT("Nuageux"), TEXT("Pluie"), TEXT("Orage"), TEXT("Brouillard"), TEXT("Neige") };
		return N[(int32)W];
	}

	FString CapsuleName(ECapsuleTier T)
	{
		static const TCHAR* N[] = { TEXT("Micro-capsule"), TEXT("Ultra-capsule"), TEXT("Capsule Prisme") };
		return N[(int32)T];
	}

	float CapsuleMultiplier(ECapsuleTier T)
	{
		static const float M[] = { 1.f, 1.8f, 3.5f };
		return M[(int32)T];
	}

	FLinearColor CapsuleColor(ECapsuleTier T)
	{
		switch (T)
		{
		case ECapsuleTier::Ultra: return FLinearColor(1.0f, 0.55f, 0.1f);
		case ECapsuleTier::Prism: return FLinearColor(0.9f, 0.3f, 1.0f);
		default:                  return FLinearColor(0.3f, 0.9f, 1.0f);
		}
	}

	FString DisplayNameOf(const FCreatureInstance& Inst, const FSpeciesDef* Species)
	{
		if (!Inst.Nickname.IsEmpty()) return Inst.Nickname;
		return Species ? Species->DisplayName : Inst.SpeciesId.ToString();
	}
}
