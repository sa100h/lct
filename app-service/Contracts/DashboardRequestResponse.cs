namespace AppService.Contracts;

public sealed record DashboardRequestResponse(
    Guid Id,
    string Description,
    int ObjectId,
    string ObjectName,
    string Status);
