namespace AppService.Models;

public sealed record ForecastHistoryObject(
    int Id,
    int? ParentId,
    string Name,
    double Latitude,
    double Longitude,
    IReadOnlyList<string> Statuses,
    bool? HasHighRisk,
    IReadOnlyList<string> OwnStatuses,
    int OwnChannelCount,
    bool IsErroneous);
