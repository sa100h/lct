namespace AppService.Services.Infrastructure;

public sealed class RoleAccessOptions
{
    public const string SectionName = "RoleAccess";

    public List<RoleDefinitionOptions> Roles { get; set; } = [];
}
