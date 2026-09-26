namespace AppService.Contracts;

public sealed record DashboardResponse(
    DashboardObjectsResponse Objects,
    IReadOnlyList<DashboardEventResponse> Events,
    IReadOnlyList<DashboardForecastResponse> Forecasts,
    IReadOnlyList<DashboardRequestResponse> Requests);
