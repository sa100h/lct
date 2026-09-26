namespace AppService.Contracts;

public sealed record DashboardForecastResponse(Guid Id, DateTimeOffset CreatedAt, string Status);
