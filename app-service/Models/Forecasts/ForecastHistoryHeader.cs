namespace AppService.Models;

public sealed record ForecastHistoryHeader(
    Guid Id,
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    DateTimeOffset? StartCompositionTime,
    DateTimeOffset? EndCompositionTime,
    string JournalStatus,
    string? ApprovedByLogin,
    DateTimeOffset? ApprovedAt,
    IReadOnlyList<int>? DispatcherObjectIds);
