using AppService.Contracts;

namespace AppService.Services.Domain;

public interface IEventFeedClient
{
    Task<EventFeedPageDto> GetEventsAsync(
        DateTimeOffset from,
        DateTimeOffset to,
        string? cursor,
        CancellationToken cancellationToken = default);
}

