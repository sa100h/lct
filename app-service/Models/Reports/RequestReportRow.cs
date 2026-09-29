namespace AppService.Models;

public sealed record RequestReportRow(
    DateTimeOffset CreatedAt,
    string Description,
    string ObjectName,
    string Status,
    string DispatcherLogin,
    string TechnicianLogin);
