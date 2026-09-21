namespace AppService.Contracts;

public sealed record EventFeedPageDto(
    DateTimeOffset From,
    DateTimeOffset To,
    IReadOnlyList<EventFeedEventDto> Items,
    bool HasMore,
    string? NextCursor);

