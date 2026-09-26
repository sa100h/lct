namespace AppService.Models;

public sealed record DashboardRequestRow(
    Guid Id,
    string Description,
    int ObjectId,
    string ObjectName,
    string Status);
