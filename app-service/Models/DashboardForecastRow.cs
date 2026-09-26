namespace AppService.Models;

public sealed record DashboardForecastRow(
    Guid Id,
    DateTimeOffset CreatedAt,
    DateTimeOffset? StartCompositionTime,
    DateTimeOffset? EndCompositionTime);
