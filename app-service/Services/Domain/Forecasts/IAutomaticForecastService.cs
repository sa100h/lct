namespace AppService.Services.Domain;

public interface IAutomaticForecastService
{
    Task<bool> RunCurrentHourAsync(CancellationToken cancellationToken = default);
}
