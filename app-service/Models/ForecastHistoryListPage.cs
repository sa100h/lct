namespace AppService.Models;

public sealed record ForecastHistoryListPage(
    IReadOnlyList<ForecastHistoryListItem> Items,
    int Total);
