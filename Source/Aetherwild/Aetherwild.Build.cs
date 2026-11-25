using UnrealBuildTool;

public class Aetherwild : ModuleRules
{
	public Aetherwild(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput",
			"AIModule", "Json", "JsonUtilities", "AssetRegistry"
		});
	}
}
