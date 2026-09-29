namespace AppService.Services.Domain;

public interface IForecastApproveService
{
    Task ApproveAsync(
        Guid journalId,
        Guid userId,
        CancellationToken cancellationToken = default);
}
