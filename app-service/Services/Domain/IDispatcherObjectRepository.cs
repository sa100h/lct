using AppService.Models;

namespace AppService.Services.Domain;

public interface IDispatcherObjectRepository
{
    Task<IReadOnlyList<DispatcherObjectInfo>> GetAllWithDescendantStatusesAsync(
        CancellationToken cancellationToken = default);
}
