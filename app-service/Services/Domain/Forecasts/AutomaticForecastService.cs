namespace AppService.Services.Domain;

public sealed class AutomaticForecastService(
    IAutomaticForecastRepository repository,
    TimeProvider timeProvider) : IAutomaticForecastService
{
    public async Task<bool> RunCurrentHourAsync(CancellationToken cancellationToken = default)
    {
        var now = timeProvider.GetUtcNow();
        var scheduledHour = new DateTimeOffset(
            now.Year, now.Month, now.Day, now.Hour, 0, 0, TimeSpan.Zero);
        return await repository.RunHourlyAsync(
            scheduledHour,
            now.AddDays(-1),
            now,
            cancellationToken);
    }
}
