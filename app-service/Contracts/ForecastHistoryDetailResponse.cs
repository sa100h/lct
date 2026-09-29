namespace AppService.Contracts;

public sealed record ForecastHistoryDetailResponse(
    Guid Id,
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    string Status,
    string? ApprovedByLogin,
    DateTimeOffset? ApprovedAt,
    IReadOnlyList<ForecastHistoryObjectResponse> Objects);
