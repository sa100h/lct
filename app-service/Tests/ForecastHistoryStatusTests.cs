using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ForecastHistoryStatusTests
{
    private static readonly DateTimeOffset Start = new(2026, 9, 1, 10, 0, 0, TimeSpan.Zero);
    private static readonly DateTimeOffset End = new(2026, 9, 1, 11, 0, 0, TimeSpan.Zero);

    [Fact]
    public void Resolve_ApprovedColumn_WinsOverDoneTimes()
        => Assert.Equal("approved", ForecastHistoryStatus.Resolve("approved", Start, End));

    [Fact]
    public void Resolve_DoneTimesWithoutApproved_IsDone()
        => Assert.Equal("done", ForecastHistoryStatus.Resolve("done", Start, End));

    [Fact]
    public void Resolve_IgnoresErrorColumn_UsesTimes()
        => Assert.Equal("done", ForecastHistoryStatus.Resolve("error", Start, End));

    [Fact]
    public void Resolve_PendingTimes()
        => Assert.Equal("pending", ForecastHistoryStatus.Resolve("pending", null, null));
}
