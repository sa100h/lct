using AppService.Contracts;
using AppService.Services.Domain;

namespace AppService.Services.Infrastructure;

public sealed class EventFeedPollingWorker(
    IEventFeedClient client,
    IEventBatchHandler handler,
    EventFeedOptions options,
    TimeProvider timeProvider,
    ILogger<EventFeedPollingWorker> logger) : BackgroundService
{
    private readonly Dictionary<long, DateTimeOffset> recentlyHandled = [];

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            await PollSafelyAsync(stoppingToken);

            try
            {
                await Task.Delay(options.PollInterval, timeProvider, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
        }
    }

    internal async Task PollOnceAsync(CancellationToken cancellationToken)
    {
        var to = timeProvider.GetUtcNow();
        var from = to - options.Lookback;
        var accepted = new List<EventFeedEventDto>();
        var seenThisPoll = new HashSet<long>();
        var received = 0;
        var duplicates = 0;
        var pages = 0;
        string? cursor = null;

        do
        {
            var page = await client.GetEventsAsync(from, to, cursor, cancellationToken);
            pages++;
            received += page.Items.Count;

            foreach (var item in page.Items)
            {
                if (recentlyHandled.ContainsKey(item.Id) || !seenThisPoll.Add(item.Id))
                {
                    duplicates++;
                    continue;
                }

                accepted.Add(item);
            }

            cursor = page.HasMore
                ? page.NextCursor ?? throw new InvalidOperationException("Event feed page has no continuation cursor.")
                : null;

            if (pages >= 10_000)
            {
                throw new InvalidOperationException("Event feed pagination exceeded the safety limit.");
            }
        } while (cursor is not null);

        await handler.HandleAsync(accepted, cancellationToken);
        foreach (var item in accepted)
        {
            recentlyHandled[item.Id] = item.OccurredAt;
        }
        RemoveExpiredIds(to - options.Lookback - options.PollInterval);

        logger.LogInformation(
            "Event feed poll completed: From={From}, To={To}, Received={Received}, Duplicates={Duplicates}, Accepted={Accepted}, Pages={Pages}",
            from,
            to,
            received,
            duplicates,
            accepted.Count,
            pages);
    }

    private async Task PollSafelyAsync(CancellationToken cancellationToken)
    {
        try
        {
            await PollOnceAsync(cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // Normal host shutdown.
        }
        catch (Exception exception)
        {
            logger.LogWarning(exception, "Event feed poll failed; the next scheduled poll will retry.");
        }
    }

    private void RemoveExpiredIds(DateTimeOffset threshold)
    {
        foreach (var id in recentlyHandled
                     .Where(pair => pair.Value < threshold)
                     .Select(pair => pair.Key)
                     .ToArray())
        {
            recentlyHandled.Remove(id);
        }
    }
}
