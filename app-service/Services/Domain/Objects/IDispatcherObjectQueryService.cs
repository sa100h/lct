using AppService.Models;

namespace AppService.Services.Domain;

public interface IDispatcherObjectQueryService
{
    Task<IReadOnlyList<DispatcherObjectInfo>> GetAllAsync(
        CancellationToken cancellationToken = default);
}
