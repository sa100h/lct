namespace AppService.Models;

public sealed record RequestHeader(
    Guid Id,
    DateTimeOffset CreatedAt,
    string Description,
    string Status,
    string DispatcherLogin,
    string TechnicianLogin,
    int? Priority,
    int ObjectId,
    string ObjectName,
    IReadOnlyList<int> DispatcherObjectIds);
