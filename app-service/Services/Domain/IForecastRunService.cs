using AppService.Models;

namespace AppService.Services.Domain;

public interface IForecastRunService
{
    Task<ForecastJournalEntry> RunAsync(
        Guid userId,
        IReadOnlyCollection<int>? dispatcherObjectIds,
        CancellationToken cancellationToken = default);
}
