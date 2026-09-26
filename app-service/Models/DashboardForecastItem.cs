namespace AppService.Models;

public sealed record DashboardForecastItem(Guid Id, DateTimeOffset CreatedAt, string Status);
