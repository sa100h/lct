namespace AppService.Contracts;

public sealed record ForecastHistoryListResponse(
    IReadOnlyList<ForecastHistoryListItemResponse> Items,
    int Total);
