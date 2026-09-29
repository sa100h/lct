using AppService.Models;

namespace AppService.Services.Domain;

public interface IRequestCommandService
{
    Task<Guid> CreateAsync(
        Guid dispatcherUserId,
        CreateRequestCommand command,
        CancellationToken cancellationToken = default);

    Task UpdateStatusAsync(
        Guid id,
        bool seesAll,
        Guid userId,
        string status,
        CancellationToken cancellationToken = default);
}
