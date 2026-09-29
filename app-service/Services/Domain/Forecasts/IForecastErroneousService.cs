namespace AppService.Services.Domain;

public interface IForecastErroneousService
{
    Task MarkAsync(
        Guid journalId,
        Guid dispatcherUserId,
        int dispatcherObjectId,
        CancellationToken cancellationToken = default);
}
