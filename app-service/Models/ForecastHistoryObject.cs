namespace AppService.Models;

public sealed record ForecastHistoryObject(
    int Id,
    int? ParentId,
    string Name,
    double Latitude,
    double Longitude,
    IReadOnlyList<string> Statuses,
    bool HasHighRisk);
