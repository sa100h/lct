namespace AppService.Services.Infrastructure;

public sealed class RoleDefinitionOptions
{
    public string Code { get; set; } = string.Empty;
    public string GroupDn { get; set; } = string.Empty;
    public List<string> Permissions { get; set; } = [];
}
