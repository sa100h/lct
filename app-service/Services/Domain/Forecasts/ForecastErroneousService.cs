namespace AppService.Services.Domain;

public sealed class ForecastErroneousService(
    IForecastResultRepository results,
    IForecastJournalRepository journal,
    IDispatcherObjectRepository objects) : IForecastErroneousService
{
    public const string MissingJournal = "Прогноз не найден.";
    public const string MissingObject = "Объект не найден.";
    public const string EmptyObjects = "Выберите объекты.";

    public async Task MarkAsync(
        Guid journalId,
        Guid dispatcherUserId,
        IReadOnlyList<int> dispatcherObjectIds,
        CancellationToken cancellationToken = default)
    {
        if (dispatcherObjectIds is null || dispatcherObjectIds.Count == 0)
        {
            throw new ArgumentException(EmptyObjects);
        }

        var header = await journal.GetHeaderAsync(journalId, cancellationToken);
        if (header is null)
        {
            throw new KeyNotFoundException(MissingJournal);
        }

        var all = await objects.GetAllWithDescendantStatusesAsync(cancellationToken);
        var allowed = ForecastJournalTree.AllowedIds(header.DispatcherObjectIds, all);
        if (dispatcherObjectIds.Any(id => !allowed.Contains(id)))
        {
            throw new ArgumentException(MissingObject);
        }

        await results.MarkErroneousAsync(
            journalId,
            dispatcherUserId,
            dispatcherObjectIds.Distinct().ToArray(),
            cancellationToken);
    }
}
