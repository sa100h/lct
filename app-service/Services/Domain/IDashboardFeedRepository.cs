using AppService.Models;

namespace AppService.Services.Domain;

public interface IDashboardFeedRepository
{
    Task<IReadOnlyList<DashboardEventRow>> GetRecentEventsAsync(
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<DashboardForecastRow>> GetRecentForecastsAsync(
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<DashboardRequestRow>> GetRecentRequestsAsync(
        CancellationToken cancellationToken = default);
}
