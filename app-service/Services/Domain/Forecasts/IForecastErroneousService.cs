namespace AppService.Services.Domain;

public interface IForecastErroneousService
{
    Task MarkAsync(
        Guid journalId,
        Guid dispatcherUserId,
        IReadOnlyList<int> dispatcherObjectIds,
        CancellationToken cancellationToken = default);
}
