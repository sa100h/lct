namespace AppService.Contracts;

public sealed record RequestDetailObjectResponse(
    int Id,
    int? ParentId,
    string Name,
    double Latitude,
    double Longitude,
    IReadOnlyList<string> Statuses,
    IReadOnlyList<string> OwnStatuses,
    int OwnChannelCount);
