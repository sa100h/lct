namespace AppService.Contracts;

public sealed record DashboardResponse(
    DashboardObjectsResponse Objects,
    IReadOnlyList<DashboardDayCountResponse> AlarmsByDay,
    int RequestsTotal,
    IReadOnlyList<DashboardStatusCountResponse> RequestsByStatus,
    IReadOnlyList<DashboardDayCountResponse> RequestsByDay,
    IReadOnlyList<DashboardStatusCountResponse> ForecastsByStatus);
