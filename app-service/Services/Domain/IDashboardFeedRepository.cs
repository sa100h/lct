using AppService.Models;

namespace AppService.Services.Domain;

public interface IDashboardFeedRepository
{
    Task<IReadOnlyDictionary<DateOnly, int>> GetAlarmCountsByDayAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<DashboardStatusCount>> GetRequestCountsByStatusAsync(
        CancellationToken cancellationToken = default);

    Task<IReadOnlyDictionary<DateOnly, int>> GetRequestCountsByDayAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<DashboardStatusCount>> GetForecastCountsByStatusAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default);
}
