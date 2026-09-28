namespace AppService.Models;

public sealed record ForecastChannelSnapshot(
    IReadOnlyDictionary<int, string> Readings,
    IReadOnlyCollection<int> ActiveChannelIds);
