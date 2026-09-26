namespace AppService.Contracts;

public sealed record DashboardEventResponse(
    long Id,
    DateTimeOffset OccurredAt,
    int ObjectId,
    string ObjectName,
    string ChannelName,
    bool IsAlarm,
    string? Value);
