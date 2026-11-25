// AETHERWILD - Cycle jour/nuit + meteo dynamique. Pilote le soleil, la lune, le brouillard et le ciel.
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AetherTypes.h"
#include "AetherWorldSubsystem.generated.h"

class ADirectionalLight;
class AExponentialHeightFog;
class ASkyLight;

UCLASS()
class AETHERWILD_API UAetherWorldSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

	static UAetherWorldSubsystem* Get(const UObject* WorldContext);

	/** Heure de 0 a 24. */
	UPROPERTY(BlueprintReadWrite) float TimeOfDay = 8.5f;
	/** Duree d'une journee complete, en minutes reelles. */
	UPROPERTY(BlueprintReadWrite) float DayLengthMinutes = 32.f;
	UPROPERTY(BlueprintReadOnly) EWeatherType Weather = EWeatherType::Clear;

	EDayPhase GetPhase() const;
	bool IsNight() const { return GetPhase() == EDayPhase::Night; }
	bool MatchesPhase(EDayPhase Rule) const { return Rule == EDayPhase::Any || Rule == GetPhase(); }
	bool MatchesWeather(const TArray<EWeatherType>& Allowed) const { return Allowed.Num() == 0 || Allowed.Contains(Weather); }
	FString GetClockString() const;

	void SetWeather(EWeatherType NewWeather, bool bInstant = false);
	void SkipHours(float Hours) { TimeOfDay = FMath::Fmod(TimeOfDay + Hours + 24.f, 24.f); }

	/** 0..1 : intensite visuelle de la meteo (pluie, orage...) lissee dans le temps. */
	float GetWeatherBlend() const { return WeatherBlend; }

private:
	void FindSceneActors();
	void ApplyLighting(float DeltaTime);
	void RollNextWeather();
	void UpdateBiomeAmbience(float DeltaTime);

	TWeakObjectPtr<ADirectionalLight> Sun;
	TWeakObjectPtr<ADirectionalLight> Moon;
	TWeakObjectPtr<AExponentialHeightFog> Fog;
	TWeakObjectPtr<ASkyLight> Sky;
	float BaseSunIntensity = 10.f;
	float BaseMoonIntensity = 0.4f;
	float BaseFogDensity = 0.02f;
	float WeatherBlend = 0.f;
	float WeatherHoursLeft = 6.f;
	float BiomeVolcano = 0.f;
	float BiomeForest = 0.f;
	float BiomeAltitude = 0.f;
	FRandomStream Rng;
};
