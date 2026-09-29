namespace AppService.Models;

public sealed record DashboardSnapshot(
    DashboardObjectSummary Objects,
    IReadOnlyList<DashboardDayCount> AlarmsByDay,
    int RequestsTotal,
    IReadOnlyList<DashboardStatusCount> RequestsByStatus,
    IReadOnlyList<DashboardDayCount> RequestsByDay,
    IReadOnlyList<DashboardStatusCount> ForecastsByStatus);
