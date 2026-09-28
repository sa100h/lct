namespace AppService.Contracts;

public sealed record RequestListItemResponse(
    Guid Id,
    DateTimeOffset CreatedAt,
    string Description,
    int ObjectId,
    string ObjectName,
    string Status,
    string DispatcherLogin,
    string TechnicianLogin);
