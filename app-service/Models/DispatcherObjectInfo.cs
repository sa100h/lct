namespace AppService.Models;

public sealed record DispatcherObjectInfo(
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
