using AppService.Models;

namespace AppService.Services.Domain;

public interface IForecastResultRepository
{
    Task<bool> JournalExistsAsync(Guid journalId, CancellationToken cancellationToken = default);
    Task MarkErroneousAsync(
        Guid journalId,
        Guid dispatcherUserId,
        IReadOnlyList<int> objectIds,
        CancellationToken cancellationToken = default);
    Task MarkRequestCreatedAsync(
        Guid journalId,
        Guid dispatcherUserId,
        IReadOnlyList<int> objectIds,
        CancellationToken cancellationToken = default);
    Task<IReadOnlyDictionary<int, ForecastJournalResult>> ListByJournalAsync(
        Guid journalId,
        CancellationToken cancellationToken = default);
}
