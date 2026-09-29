using AppService.Services.Infrastructure;
using Xunit;

namespace AppService.Tests;

public sealed class ForecastOptionsTests
{
    [Fact]
    public void ThresholdFor_UsesCategoryThenFallback()
    {
        var options = new ForecastOptions
        {
            RiskThreshold = 0.5,
            RiskThresholds =
            {
                ["sensor-failure"] = 0.27,
                ["fire-risk"] = 0.551,
            },
        };
        Assert.Equal(0.27, options.ThresholdFor("sensor-failure"));
        Assert.Equal(0.551, options.ThresholdFor("fire-risk"));
        Assert.Equal(0.5, options.ThresholdFor("other"));
    }

    [Fact]
    public void ThresholdFor_EmptyMap_IsAlwaysFallback()
    {
        var options = new ForecastOptions { RiskThreshold = 0.75 };
        Assert.Equal(0.75, options.ThresholdFor("sensor-failure"));
    }
}
