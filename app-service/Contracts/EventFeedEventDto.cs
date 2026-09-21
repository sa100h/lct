namespace AppService.Contracts;

public sealed record EventFeedEventDto(
    long Id,
    long ChannelId,
    DateTimeOffset OccurredAt,
    DateTimeOffset SourceOccurredAt,
    bool IsAlarm,
    string Value);

