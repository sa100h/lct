using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ForecastRiskTests
{
    private const double Threshold = 0.4;

    [Fact]
    public void FromDescription_NullOrEmptyJson_IsNull()
    {
        Assert.Null(ForecastRisk.FromDescription(null, Threshold));
        Assert.Null(ForecastRisk.FromDescription("", Threshold));
        Assert.Null(ForecastRisk.FromDescription("{}", Threshold));
        Assert.Null(ForecastRisk.FromDescription("""{"channels":{}}""", Threshold));
    }

    [Fact]
    public void FromDescription_AnyValueAtOrAboveThreshold_IsTrue()
    {
        var json = """{"channels":{"1":{"fire-risk":{"value":0.4},"sensor-failure":{"value":0.1}}}}""";
        Assert.True(ForecastRisk.FromDescription(json, Threshold));
    }

    [Fact]
    public void FromDescription_AllValuesBelowThreshold_IsFalse()
    {
        var json = """{"channels":{"1":{"fire-risk":{"value":0.39}}}}""";
        Assert.False(ForecastRisk.FromDescription(json, Threshold));
    }

    [Fact]
    public void FromDescription_UsesPassedThresholdNotHalf()
    {
        var json = """{"channels":{"1":{"fire-risk":{"value":0.6}}}}""";
        Assert.False(ForecastRisk.FromDescription(json, 0.7));
        Assert.True(ForecastRisk.FromDescription(json, 0.5));
    }

    [Fact]
    public void Parse_UnpredictableOnly_HasNullRiskAndNoValues()
    {
        var json = """{"channels":{"120116":{"sensor-failure":{"status_code":"unpredictable"}}}}""";
        var parsed = ForecastRisk.Parse(json, Threshold);
        Assert.Null(parsed.HighRisk);
        Assert.Empty(parsed.Values);
    }

    [Fact]
    public void Parse_CollectsNumericValuesAndRisk()
    {
        var json = """{"channels":{"120578":{"fire-risk":{"value":0.81},"sensor-failure":{"status_code":"unpredictable"}}}}""";
        var parsed = ForecastRisk.Parse(json, 0.5);
        Assert.True(parsed.HighRisk);
        var item = Assert.Single(parsed.Values);
        Assert.Equal("120578", item.ChannelId);
        Assert.Equal("fire-risk", item.Category);
        Assert.Equal(0.81, item.Value);
    }
}
