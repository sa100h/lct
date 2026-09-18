namespace AppService.Models;

public sealed record DirectoryIdentity(
    Guid Id,
    string Login,
    bool IsActive,
    IReadOnlyList<string> Groups);
