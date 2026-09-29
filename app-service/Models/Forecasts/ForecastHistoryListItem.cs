namespace AppService.Models;

public sealed record ForecastHistoryListItem(
    Guid Id,
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    string Status,
    int ObjectCount);
