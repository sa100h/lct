namespace AppService.Models;

public sealed record ForecastHistoryDetail(
    Guid Id,
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    string Status,
    IReadOnlyList<ForecastHistoryObject> Objects);
