using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ReportPeriodTests
{
    [Fact]
    public void TryCreate_SingleDay_IsMoscowMidnightToNext()
    {
        Assert.True(ReportPeriod.TryCreate(new DateOnly(2026, 9, 28), new DateOnly(2026, 9, 28), out var range));
        Assert.Equal(new DateTimeOffset(2026, 9, 27, 21, 0, 0, TimeSpan.Zero), range.FromInclusive);
        Assert.Equal(new DateTimeOffset(2026, 9, 28, 21, 0, 0, TimeSpan.Zero), range.ToExclusive);
    }

    [Fact]
    public void TryCreate_RejectsInvertedAndTooLong()
    {
        Assert.False(ReportPeriod.TryCreate(new DateOnly(2026, 9, 2), new DateOnly(2026, 9, 1), out _));
        Assert.False(ReportPeriod.TryCreate(new DateOnly(2026, 1, 1), new DateOnly(2026, 4, 4), out _));
        Assert.True(ReportPeriod.TryCreate(new DateOnly(2026, 1, 1), new DateOnly(2026, 4, 3), out _));
    }
}
