using AppService.Contracts;
using AppService.Models;
using AppService.Services.Domain;

namespace AppService.Services.Infrastructure;

public sealed class PersistingEventBatchHandler(
    IEventLogRepository repository,
    ILogger<PersistingEventBatchHandler> logger) : IEventBatchHandler
{
    private const int UnknownChannelLogLimit = 20;

    public async Task HandleAsync(
        IReadOnlyCollection<EventFeedEventDto> events,
        CancellationToken cancellationToken = default)
    {
        if (events.Count == 0)
        {
            return;
        }

        var entries = events
            .Select(item => new EventLogEntry(
                item.Id,
                item.ChannelId,
                item.OccurredAt,
                item.IsAlarm,
                item.Value))
            .ToArray();
        var result = await repository.InsertAsync(entries, cancellationToken);

        if (result.UnknownEventCount > 0)
        {
            var displayedChannelIds = result.UnknownChannelIds
                .Take(UnknownChannelLogLimit);
            logger.LogWarning(
                "Skipped event feed records for unknown sensor channels: Events={UnknownEvents}, Channels={UnknownChannels}, ChannelIds={ChannelIds}",
                result.UnknownEventCount,
                result.UnknownChannelIds.Count,
                string.Join(',', displayedChannelIds));
        }

        logger.LogInformation(
            "Handled event feed batch: Count={Count}, Inserted={Inserted}, Duplicates={Duplicates}, Skipped={Skipped}, Alarms={Alarms}, From={From}, To={To}",
            events.Count,
            result.InsertedCount,
            result.DuplicateCount,
            result.UnknownEventCount,
            events.Count(item => item.IsAlarm),
            events.Min(item => item.OccurredAt),
            events.Max(item => item.OccurredAt));
    }
}
