namespace AppService.Contracts;

public sealed record ForecastHistoryListItemResponse(
    Guid Id,
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    string Status,
    int ObjectCount,
    string? ApprovedByLogin,
    DateTimeOffset? ApprovedAt);
