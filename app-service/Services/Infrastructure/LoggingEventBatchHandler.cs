using AppService.Contracts;
using AppService.Services.Domain;

namespace AppService.Services.Infrastructure;

public sealed class LoggingEventBatchHandler(ILogger<LoggingEventBatchHandler> logger) : IEventBatchHandler
{
    public Task HandleAsync(
        IReadOnlyCollection<EventFeedEventDto> events,
        CancellationToken cancellationToken = default)
    {
        if (events.Count == 0)
        {
            return Task.CompletedTask;
        }

        logger.LogInformation(
            "Received event feed batch: Count={Count}, Alarms={Alarms}, From={From}, To={To}",
            events.Count,
            events.Count(item => item.IsAlarm),
            events.Min(item => item.OccurredAt),
            events.Max(item => item.OccurredAt));
        return Task.CompletedTask;
    }
}

