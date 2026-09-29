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
        IReadOnlyDictionary<int, string> channelReadings,
        IReadOnlyList<int>? dispatcherObjectIds,
        DateTimeOffset createdAt,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<ForecastAuthor>> ListAuthorsAsync(
        CancellationToken cancellationToken = default);

    Task<(IReadOnlyList<ForecastHistoryListRow> Items, int Total)> ListRowsAsync(
        Guid? createdBy,
        DateOnly? from,
        DateOnly? to,
        int offset,
        int limit,
        CancellationToken cancellationToken = default);

    Task<ForecastHistoryHeader?> GetHeaderAsync(
        Guid id,
        CancellationToken cancellationToken = default);
}
