using AppService.Models;
using AppService.Services.Domain;
using Xunit;

namespace AppService.Tests;

public sealed class ForecastChannelNamesTests
{
    [Fact]
    public void NumericIds_ParsesDistinctIntegers()
    {
        IReadOnlyList<ForecastChannelValue> values =
        [
            new("196623", "infrastructure-wear", 0.59),
            new("a", "fire-risk", 0.1),
            new("196623", "sensor-failure", 0.2),
            new("196624", "infrastructure-wear", 0.3),
        ];

        Assert.Equal([196623, 196624], ForecastChannelNames.NumericIds(values));
    }

    [Fact]
    public void Attach_UsesLookupNameAndFallsBackToChannelId()
    {
        IReadOnlyList<ForecastChannelValue> values =
        [
            new("196623", "infrastructure-wear", 0.59),
            new("196624", "infrastructure-wear", 0.4),
            new("x", "fire-risk", 0.1),
        ];
        IReadOnlyDictionary<int, string> names = new Dictionary<int, string>
        {
            [196623] = "ДУ",
        };

        var attached = ForecastChannelNames.Attach(values, names);

        Assert.Equal("ДУ", attached[0].SensorName);
        Assert.Equal("196623", attached[0].ChannelId);
        Assert.Equal("196624", attached[1].SensorName);
        Assert.Equal("x", attached[2].SensorName);
        Assert.Equal("196623", values[0].SensorName);
    }
}
