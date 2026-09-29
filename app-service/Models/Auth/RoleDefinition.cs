namespace AppService.Models;

public sealed record RoleDefinition(
    string Code,
    string GroupDn,
    IReadOnlyList<string> Permissions);
