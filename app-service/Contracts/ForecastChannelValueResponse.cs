namespace AppService.Contracts;

public sealed record ForecastChannelValueResponse(string ChannelId, string Category, double Value);
