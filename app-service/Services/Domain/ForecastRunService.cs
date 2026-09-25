using AppService.Models;

namespace AppService.Services.Domain;

public sealed class ForecastRunService(
    IForecastJournalRepository repository,
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

        return await repository.CreateAsync(
            userId,
            Description,
            normalizedObjectIds,
            timeProvider.GetUtcNow(),
            cancellationToken);
    }
}
