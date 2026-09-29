namespace AppService.Services.Domain;

public sealed class ForecastApproveService(
    IForecastJournalRepository journal,
    TimeProvider clock) : IForecastApproveService
{
    public const string MissingJournal = "Прогноз не найден.";
    public const string NotDone = "Прогноз ещё не готов.";
    public const string AlreadyApproved = "Прогноз уже обработан.";

    public async Task ApproveAsync(
        Guid journalId,
        Guid userId,
        CancellationToken cancellationToken = default)
    {
        var header = await journal.GetHeaderAsync(journalId, cancellationToken);
        if (header is null)
        {
            throw new KeyNotFoundException(MissingJournal);
        }

        if (string.Equals(header.JournalStatus, ForecastHistoryStatus.Approved, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(AlreadyApproved);
        }

        if (DashboardQueryService.MapForecastStatus(
                header.StartCompositionTime,
                header.EndCompositionTime) != "done")
        {
            throw new ArgumentException(NotDone);
        }

        var updated = await journal.ApproveAsync(journalId, userId, clock.GetUtcNow(), cancellationToken);
        if (!updated)
        {
            throw new InvalidOperationException(AlreadyApproved);
        }
    }
}
