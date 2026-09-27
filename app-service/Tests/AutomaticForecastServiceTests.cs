using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class AutomaticForecastServiceTests
{
    [Fact]
    public async Task RunCurrentHourAsync_UsesUtcHourAndRollingDay()
    {
        var now = new DateTimeOffset(2026, 9, 27, 12, 34, 56, TimeSpan.Zero);
        var repository = new RecordingAutomaticForecastRepository();
        var service = new AutomaticForecastService(repository, new FixedTimeProvider(now));

        await service.RunCurrentHourAsync(TestContext.Current.CancellationToken);

        Assert.Equal(new DateTimeOffset(2026, 9, 27, 12, 0, 0, TimeSpan.Zero), repository.ScheduledHour);
        Assert.Equal(now.AddDays(-1), repository.From);
        Assert.Equal(now, repository.To);
    }

    private sealed class RecordingAutomaticForecastRepository : IAutomaticForecastRepository
    {
        public DateTimeOffset ScheduledHour { get; private set; }
        public DateTimeOffset From { get; private set; }
        public DateTimeOffset To { get; private set; }

        public Task<bool> RunHourlyAsync(
            DateTimeOffset scheduledHour,
            DateTimeOffset from,
            DateTimeOffset to,
            CancellationToken cancellationToken = default)
        {
            ScheduledHour = scheduledHour;
            From = from;
            To = to;
            return Task.FromResult(true);
        }
    }

    private sealed class FixedTimeProvider(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }
}
