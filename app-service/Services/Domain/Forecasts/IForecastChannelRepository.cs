using AppService.Models;

namespace AppService.Services.Domain;

public interface IForecastChannelRepository
{
    Task<ForecastChannelSnapshot> GetLatestForObjectsAsync(
        IReadOnlyCollection<int>? dispatcherObjectIds,
        DateTimeOffset from,
        DateTimeOffset to,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyDictionary<int, string>> GetNamesByIdsAsync(
        IReadOnlyCollection<int> channelIds,
        CancellationToken cancellationToken = default);
}
