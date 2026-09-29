using AppService.Services.Domain;

namespace AppService.Services.Infrastructure;

public sealed class ForecastHourlyWorker(
    IServiceScopeFactory scopeFactory,
    TimeProvider timeProvider,
    ILogger<ForecastHourlyWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = scopeFactory.CreateScope();
                var service = scope.ServiceProvider.GetRequiredService<IAutomaticForecastService>();
                var created = await service.RunCurrentHourAsync(stoppingToken);
                logger.LogInformation("Hourly forecast completed; journal created: {Created}", created);

                var now = timeProvider.GetUtcNow();
                var nextHour = new DateTimeOffset(
                    now.Year, now.Month, now.Day, now.Hour, 0, 0, TimeSpan.Zero).AddHours(1);
                await Task.Delay(nextHour - now, timeProvider, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                logger.LogError(exception, "Hourly forecast failed; retrying in one minute");
                try
                {
                    await Task.Delay(TimeSpan.FromMinutes(1), timeProvider, stoppingToken);
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    break;
                }
            }
        }
    }
}
