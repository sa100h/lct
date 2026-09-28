namespace AppService.Models;

public sealed record DashboardSnapshot(
    DashboardObjectSummary Objects,
    IReadOnlyList<DashboardEventRow> Events,
    IReadOnlyList<DashboardForecastItem> Forecasts);
