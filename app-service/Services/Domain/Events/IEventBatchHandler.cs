using AppService.Contracts;

namespace AppService.Services.Domain;

public interface IEventBatchHandler
{
    Task HandleAsync(
        IReadOnlyCollection<EventFeedEventDto> events,
        CancellationToken cancellationToken = default);
}

