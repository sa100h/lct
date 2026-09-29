namespace AppService.Models;

public sealed record ForecastHistoryDetail(
    Guid Id,
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    string Status,
    string? ApprovedByLogin,
    DateTimeOffset? ApprovedAt,
    IReadOnlyList<ForecastHistoryObject> Objects);
