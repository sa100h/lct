namespace AppService.Models;

public sealed record ForecastHistoryHeader(
    Guid Id,
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    DateTimeOffset? StartCompositionTime,
    DateTimeOffset? EndCompositionTime,
    IReadOnlyList<int>? DispatcherObjectIds);
