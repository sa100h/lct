using AppService.Models;

namespace AppService.Services.Domain;

public sealed class ForecastRunService(
    IForecastJournalRepository repository,
    IForecastChannelRepository channels,
    TimeProvider timeProvider) : IForecastRunService
{
    private const string Description = "Запуск прогнозирования";

    public async Task<ForecastJournalEntry> RunAsync(
        Guid userId,
        IReadOnlyCollection<int>? dispatcherObjectIds,
        CancellationToken cancellationToken = default)
    {
        if (userId == Guid.Empty)
        {
            throw new ArgumentException("User id must not be empty.", nameof(userId));
        }

        IReadOnlyList<int>? normalizedObjectIds = null;
        if (dispatcherObjectIds is not null)
        {
            normalizedObjectIds = dispatcherObjectIds
                .Distinct()
                .OrderBy(id => id)
                .ToArray();

            if (normalizedObjectIds.Count == 0)
            {
                throw new ArgumentException(
                    "dispatcherObjectIds must contain at least one id or be null for all objects.",
                    nameof(dispatcherObjectIds));
            }

            var missingObjectIds = await repository.FindMissingDispatcherObjectIdsAsync(
                normalizedObjectIds,
                cancellationToken);
            if (missingObjectIds.Count > 0)
            {
                throw new ArgumentException(
                    $"Unknown dispatcher object ids: {string.Join(", ", missingObjectIds)}.",
                    nameof(dispatcherObjectIds));
            }
        }

        var now = timeProvider.GetUtcNow();
        var readings = await channels.GetLatestForObjectsAsync(
            normalizedObjectIds, now.AddDays(-1), now, cancellationToken);
        if (readings.Count == 0)
        {
            throw new ArgumentException("Нет показаний датчиков за последние 24 часа для выбранных объектов.");
        }

        return await repository.CreateAsync(
            userId,
            Description,
            readings,
            normalizedObjectIds,
            now,
            cancellationToken);
    }
}
