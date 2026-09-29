namespace AppService.Models;

public sealed record ForecastChannelValue(string ChannelId, string Category, double Value)
{
    public string SensorName { get; init; } = ChannelId;
}
