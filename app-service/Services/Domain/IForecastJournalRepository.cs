using AppService.Models;

namespace AppService.Services.Domain;

public interface IForecastJournalRepository
{
    Task<IReadOnlyList<int>> FindMissingDispatcherObjectIdsAsync(
        IReadOnlyCollection<int> dispatcherObjectIds,
        CancellationToken cancellationToken = default);

    Task<ForecastJournalEntry> CreateAsync(
        Guid userId,
        string description,
        IReadOnlyList<int>? dispatcherObjectIds,
        DateTimeOffset createdAt,
        CancellationToken cancellationToken = default);
}
