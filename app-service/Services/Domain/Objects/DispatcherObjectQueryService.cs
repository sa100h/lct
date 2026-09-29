using AppService.Models;

namespace AppService.Services.Domain;

public sealed class DispatcherObjectQueryService(
    IDispatcherObjectRepository repository) : IDispatcherObjectQueryService
{
    public Task<IReadOnlyList<DispatcherObjectInfo>> GetAllAsync(
        CancellationToken cancellationToken = default)
        => repository.GetAllWithDescendantStatusesAsync(cancellationToken);
}
