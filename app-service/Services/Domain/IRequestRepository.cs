using AppService.Models;

namespace AppService.Services.Domain;

public interface IRequestRepository
{
    Task<bool> ForecastJournalExistsAsync(Guid id, CancellationToken cancellationToken = default);
    Task<bool> IsActiveTechnicianAsync(Guid userId, CancellationToken cancellationToken = default);
    Task<Guid> InsertAsync(
        Guid forecastJournalId,
        string description,
        Guid dispatcherUserId,
        Guid technicianId,
        IReadOnlyList<int> objectIds,
        int? priority,
        CancellationToken cancellationToken = default);

    Task<(IReadOnlyList<RequestListItem> Items, int Total)> ListAsync(
        Guid? restrictToUserId,
        int offset,
        int limit,
        CancellationToken cancellationToken = default);

    Task<RequestHeader?> GetHeaderAsync(
        Guid id,
        Guid? restrictToUserId,
        CancellationToken cancellationToken = default);

    Task<bool> StatusExistsAsync(string name, CancellationToken cancellationToken = default);

    Task<bool> UpdateStatusAsync(
        Guid id,
        string statusName,
        Guid? restrictToUserId,
        CancellationToken cancellationToken = default);
}
