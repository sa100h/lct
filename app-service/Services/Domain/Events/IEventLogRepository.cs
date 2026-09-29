using AppService.Models;

namespace AppService.Services.Domain;

public interface IEventLogRepository
{
    Task<EventLogWriteResult> InsertAsync(
        IReadOnlyCollection<EventLogEntry> events,
        CancellationToken cancellationToken = default);
}
