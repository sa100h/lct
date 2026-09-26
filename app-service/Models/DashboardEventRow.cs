namespace AppService.Models;

public sealed record DashboardEventRow(
    long Id,
    DateTimeOffset OccurredAt,
    int ObjectId,
    string ObjectName,
    string ChannelName,
    bool IsAlarm,
    string? Value);
