namespace AppService.Contracts;

public sealed record ForecastHistoryDetailResponse(
    Guid Id,
    DateTimeOffset CreatedAt,
    string AuthorLogin,
    string Status,
    IReadOnlyList<ForecastHistoryObjectResponse> Objects);
