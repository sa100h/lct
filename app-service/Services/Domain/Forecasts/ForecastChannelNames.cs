using AppService.Models;

namespace AppService.Services.Domain;

public static class ForecastChannelNames
{
    public static IReadOnlyList<int> NumericIds(IEnumerable<ForecastChannelValue> values)
        => values
            .Select(item => int.TryParse(item.ChannelId, out var id) ? id : (int?)null)
            .Where(id => id.HasValue)
            .Select(id => id!.Value)
            .Distinct()
            .ToArray();

    public static IReadOnlyList<ForecastChannelValue> Attach(
        IReadOnlyList<ForecastChannelValue> values,
        IReadOnlyDictionary<int, string> names)
    {
        if (values.Count == 0)
        {
            return values;
        }

        return values
            .Select(item =>
            {
                if (int.TryParse(item.ChannelId, out var id)
                    && names.TryGetValue(id, out var sensorName)
                    && !string.IsNullOrWhiteSpace(sensorName))
                {
                    return item with { SensorName = sensorName };
                }

                return item with { SensorName = item.ChannelId };
            })
            .ToArray();
    }
}
