namespace AppService.Contracts;

public sealed record DashboardDayCountResponse(DateOnly Date, int Count);
