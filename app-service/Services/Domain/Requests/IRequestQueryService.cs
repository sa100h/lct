using AppService.Models;

namespace AppService.Services.Domain;

public interface IRequestQueryService
{
    Task<RequestListPage> ListAsync(
        bool seesAll,
        Guid userId,
        int page,
        int pageSize,
        CancellationToken cancellationToken = default);

    Task<RequestDetail?> GetAsync(
        bool seesAll,
        Guid userId,
        Guid id,
        CancellationToken cancellationToken = default);
}
