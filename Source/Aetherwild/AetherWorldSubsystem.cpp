#include "AetherWorldSubsystem.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/SkyLightComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/SkyLight.h"
#include "EngineUtils.h"
#include "CreatureDatabase.h"
#include "WorldScatter.h"
#include "Kismet/GameplayStatics.h"

void UAetherWorldSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	Rng.GenerateNewSeed();
}

bool UAetherWorldSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

TStatId UAetherWorldSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UAetherWorldSubsystem, STATGROUP_Tickables);
}

UAetherWorldSubsystem* UAetherWorldSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* W = WorldContext ? WorldContext->GetWorld() : nullptr;
	return W ? W->GetSubsystem<UAetherWorldSubsystem>() : nullptr;
}

void UAetherWorldSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	FindSceneActors();
}

void UAetherWorldSubsystem::FindSceneActors()
{
	UWorld* World = GetWorld();
	for (TActorIterator<ADirectionalLight> It(World); It; ++It)
	{
		if (It->ActorHasTag(TEXT("Moon"))) Moon = *It;
		else if (!Sun.IsValid() || It->ActorHasTag(TEXT("Sun"))) Sun = *It;
	}
	for (TActorIterator<AExponentialHeightFog> It(World); It; ++It) { Fog = *It; break; }
	for (TActorIterator<ASkyLight> It(World); It; ++It) { Sky = *It; break; }

	if (Sun.IsValid())
	{
		Sun->GetLightComponent()->SetMobility(EComponentMobility::Movable);
		BaseSunIntensity = Sun->GetLightComponent()->Intensity;
	}
	if (Moon.IsValid())
	{
		Moon->GetLightComponent()->SetMobility(EComponentMobility::Movable);
		BaseMoonIntensity = Moon->GetLightComponent()->Intensity;
	}
	if (Fog.IsValid())
	{
		BaseFogDensity = Fog->GetComponent()->FogDensity;
	}
	if (!Sun.IsValid())
	{
		UE_LOG(LogAether, Warning, TEXT("Aucune DirectionalLight : le cycle jour/nuit est inactif (lance setup_aetherwild.py)."));
	}
}

EDayPhase UAetherWorldSubsystem::GetPhase() const
{
	if (TimeOfDay >= 7.f && TimeOfDay < 18.5f) return EDayPhase::Day;
	if ((TimeOfDay >= 5.f && TimeOfDay < 7.f) || (TimeOfDay >= 18.5f && TimeOfDay < 20.5f)) return EDayPhase::Twilight;
	return EDayPhase::Night;
}

FString UAetherWorldSubsystem::GetClockString() const
{
	const int32 H = FMath::FloorToInt(TimeOfDay);
	const int32 M = FMath::FloorToInt((TimeOfDay - H) * 60.f);
	return FString::Printf(TEXT("%02d:%02d"), H, M);
}

void UAetherWorldSubsystem::SetWeather(EWeatherType NewWeather, bool bInstant)
{
	Weather = NewWeather;
	WeatherHoursLeft = Rng.FRandRange(3.f, 9.f);
	if (bInstant)
	{
		WeatherBlend = (Weather == EWeatherType::Clear) ? 0.f : 1.f;
	}
	UE_LOG(LogAether, Log, TEXT("Meteo : %s"), *Aether::WeatherName(Weather));
}

void UAetherWorldSubsystem::RollNextWeather()
{
	// Petite chaine de Markov : l'orage ne vient qu'apres la pluie, la neige est rare.
	const float R = Rng.FRand();
	switch (Weather)
	{
	case EWeatherType::Rain:  SetWeather(R < 0.4f ? EWeatherType::Storm : (R < 0.75f ? EWeatherType::Cloudy : EWeatherType::Clear)); break;
	case EWeatherType::Storm: SetWeather(R < 0.6f ? EWeatherType::Rain : EWeatherType::Cloudy); break;
	case EWeatherType::Cloudy:SetWeather(R < 0.35f ? EWeatherType::Rain : (R < 0.5f ? EWeatherType::Fog : (R < 0.58f ? EWeatherType::Snow : EWeatherType::Clear))); break;
	default:                  SetWeather(R < 0.45f ? EWeatherType::Cloudy : (R < 0.6f ? EWeatherType::Fog : EWeatherType::Clear)); break;
	}
}

void UAetherWorldSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	const float HoursPerSecond = 24.f / FMath::Max(1.f, DayLengthMinutes * 60.f);
	const float Hours = DeltaTime * HoursPerSecond;
	TimeOfDay = FMath::Fmod(TimeOfDay + Hours, 24.f);

	WeatherHoursLeft -= Hours;
	if (WeatherHoursLeft <= 0.f)
	{
		RollNextWeather();
	}
	const float Target = (Weather == EWeatherType::Clear) ? 0.f : (Weather == EWeatherType::Cloudy ? 0.4f : 1.f);
	WeatherBlend = FMath::FInterpTo(WeatherBlend, Target, DeltaTime, 0.15f);

	ApplyLighting(DeltaTime);
}

void UAetherWorldSubsystem::ApplyLighting(float DeltaTime)
{
	if (!Sun.IsValid())
	{
		static float Retry = 0.f;
		Retry += DeltaTime;
		if (Retry > 2.f) { Retry = 0.f; FindSceneActors(); }
		return;
	}

	// Lever 6h (pitch 0), midi (pitch -90), coucher 18h (pitch -180). La nuit le soleil passe sous l'horizon.
	const float SunPitch = -((TimeOfDay - 6.f) / 12.f) * 180.f;
	Sun->SetActorRotation(FRotator(SunPitch, -35.f, 0.f));

	const bool bStormy = Weather == EWeatherType::Storm || Weather == EWeatherType::Rain || Weather == EWeatherType::Snow;
	const float Dim = FMath::Lerp(1.f, bStormy ? 0.3f : 0.6f, WeatherBlend);
	Sun->GetLightComponent()->SetIntensity(BaseSunIntensity * Dim);

	if (Moon.IsValid())
	{
		Moon->SetActorRotation(FRotator(SunPitch + 180.f, 145.f, 0.f));
		const float NightAmount = FMath::Clamp((FMath::Abs(TimeOfDay - 12.f) - 6.5f) / 1.5f, 0.f, 1.f);
		Moon->GetLightComponent()->SetIntensity(BaseMoonIntensity * NightAmount * Dim);
	}

	UpdateBiomeAmbience(DeltaTime);

	if (Fog.IsValid())
	{
		float FogMul = 1.f;
		switch (Weather)
		{
		case EWeatherType::Fog:   FogMul = 9.f; break;
		case EWeatherType::Rain:  FogMul = 3.f; break;
		case EWeatherType::Storm: FogMul = 4.f; break;
		case EWeatherType::Snow:  FogMul = 4.f; break;
		case EWeatherType::Cloudy:FogMul = 1.6f; break;
		default: break;
		}
		const float Dawn = (GetPhase() == EDayPhase::Twilight) ? 1.6f : 1.f;   // brumes matinales
		// ambiance du biome ou se trouve le joueur
		const float BiomeMul = 1.f + 1.2f * BiomeForest + 2.5f * BiomeVolcano - 0.4f * BiomeAltitude;
		Fog->GetComponent()->SetFogDensity(BaseFogDensity * FMath::Lerp(1.f, FogMul, WeatherBlend) * Dawn * BiomeMul);
		FLinearColor Tint(0.45f, 0.55f, 0.75f);                                         // prairie : bleu-gris lumineux
		Tint = FMath::Lerp(Tint, FLinearColor(0.55f, 0.58f, 0.40f), BiomeForest);       // foret : vert dore
		Tint = FMath::Lerp(Tint, FLinearColor(0.62f, 0.72f, 0.95f), BiomeAltitude);     // cimes : froid et clair
		Tint = FMath::Lerp(Tint, FLinearColor(0.65f, 0.30f, 0.16f), BiomeVolcano);      // volcan : rougeoyant
		Fog->GetComponent()->SetFogInscatteringColor(Tint);
	}
}

void UAetherWorldSubsystem::UpdateBiomeAmbience(float DeltaTime)
{
	const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
	const UCreatureDatabase* DB = UCreatureDatabase::Get(this);
	if (!P || !DB) return;
	const FVector L = P->GetActorLocation();
	const float AltM = (L.Z - DB->SeaLevelZ) / 100.f;
	const float VolcM = FVector2D::Distance(FVector2D(L.X, L.Y), DB->VolcanoXY) / 100.f;
	const float TargetVolcano = 1.f - FMath::SmoothStep(900.f, 1600.f, VolcM);
	const float TargetForest = FMath::SmoothStep(0.5f, 0.75f, AWorldScatter::ForestDensityAt(FVector2D(L.X, L.Y))) * (AltM < 320.f ? 1.f : 0.f);
	const float TargetAlt = FMath::SmoothStep(300.f, 600.f, AltM);
	BiomeVolcano = FMath::FInterpTo(BiomeVolcano, TargetVolcano, DeltaTime, 0.5f);
	BiomeForest = FMath::FInterpTo(BiomeForest, TargetForest * (1.f - TargetVolcano), DeltaTime, 0.5f);
	BiomeAltitude = FMath::FInterpTo(BiomeAltitude, TargetAlt, DeltaTime, 0.5f);
}
