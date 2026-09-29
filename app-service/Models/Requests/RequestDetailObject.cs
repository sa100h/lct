namespace AppService.Models;

public sealed record RequestDetailObject(
    int Id,
    int? ParentId,
    string Name,
    double Latitude,
    double Longitude,
    IReadOnlyList<string> Statuses,
    IReadOnlyList<string> OwnStatuses,
    int OwnChannelCount);
