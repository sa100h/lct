using AppService.Models;

namespace AppService.Services.Domain;

public interface IForecastHistoryQueryService
{
    Task<IReadOnlyList<ForecastAuthor>> ListAuthorsAsync(
        CancellationToken cancellationToken = default);

    Task<ForecastHistoryListPage> ListAsync(
        ForecastHistoryListQuery query,
        CancellationToken cancellationToken = default);

    Task<ForecastHistoryDetail?> GetByIdAsync(
        Guid id,
        CancellationToken cancellationToken = default);
}
