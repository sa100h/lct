namespace AppService.Services.Domain;

public interface IAutomaticForecastRepository
{
    Task<bool> RunHourlyAsync(
        DateTimeOffset scheduledHour,
        DateTimeOffset from,
        DateTimeOffset to,
        CancellationToken cancellationToken = default);
}
