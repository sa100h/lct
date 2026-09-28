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
}
