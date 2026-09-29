namespace AppService.Services.Domain;

public sealed class ForecastErroneousService(
    IForecastResultRepository results,
    IDispatcherObjectRepository objects) : IForecastErroneousService
{
    public const string MissingJournal = "Прогноз не найден.";
    public const string MissingObject = "Объект не найден.";

    public async Task MarkAsync(
        Guid journalId,
        Guid dispatcherUserId,
        int dispatcherObjectId,
        CancellationToken cancellationToken = default)
    {
        if (!await results.JournalExistsAsync(journalId, cancellationToken))
        {
            throw new KeyNotFoundException(MissingJournal);
        }

        var objectIds = await objects.GetSubtreeIdsAsync(dispatcherObjectId, cancellationToken);
        if (objectIds.Count == 0)
        {
            throw new ArgumentException(MissingObject);
        }

        await results.MarkErroneousAsync(journalId, dispatcherUserId, objectIds, cancellationToken);
    }
}
