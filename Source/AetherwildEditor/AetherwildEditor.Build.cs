using UnrealBuildTool;

public class AetherwildEditor : ModuleRules
{
	public AetherwildEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.AddRange(new string[] { "UnrealEd", "Landscape", "ImageWrapper", "Aetherwild" });
	}
}
