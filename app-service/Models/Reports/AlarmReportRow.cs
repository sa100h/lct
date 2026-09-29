namespace AppService.Models;

public sealed record AlarmReportRow(DateTimeOffset At, string ObjectName, int ChannelId, string? Value);
