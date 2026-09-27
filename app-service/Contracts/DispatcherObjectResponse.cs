namespace AppService.Contracts;

public sealed record DispatcherObjectResponse(
    int Id,
    int? ParentId,
    string Name,
    int ObjectTypeId,
    string ObjectTypeName,
    double Longitude,
    double Latitude,
    IReadOnlyList<string> Statuses,
    int ChannelCount,
    IReadOnlyList<string> OwnStatuses,
    int OwnChannelCount);
