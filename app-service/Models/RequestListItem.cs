namespace AppService.Models;

public sealed record RequestListItem(
    Guid Id,
    DateTimeOffset CreatedAt,
    string Description,
    int ObjectId,
    string ObjectName,
    string Status,
    string DispatcherLogin,
    string TechnicianLogin);
