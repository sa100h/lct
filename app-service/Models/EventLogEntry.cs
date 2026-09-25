namespace AppService.Models;

public sealed record EventLogEntry(
    long Id,
    long SensorChannelId,
    DateTimeOffset OccurredAt,
    bool IsAlarm,
    string SensorValue);
