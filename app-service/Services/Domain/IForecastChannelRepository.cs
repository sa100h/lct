namespace AppService.Services.Domain;

public interface IForecastChannelRepository
{
    Task<IReadOnlyDictionary<int, string>> GetLatestForObjectsAsync(
        IReadOnlyCollection<int>? dispatcherObjectIds,
        DateTimeOffset from,
        DateTimeOffset to,
        CancellationToken cancellationToken = default);
}
