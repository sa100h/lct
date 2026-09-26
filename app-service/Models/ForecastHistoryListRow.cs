namespace AppService.Models;

public sealed record ForecastHistoryListRow(
    Guid Id,
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    DateTimeOffset? StartCompositionTime,
    DateTimeOffset? EndCompositionTime,
    int ObjectCount);
