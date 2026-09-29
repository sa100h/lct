using System.Text.Json;
using AppService.Models;

namespace AppService.Services.Domain;

public static class ForecastRisk
{
    private static readonly ForecastRiskParse Empty = new(null, []);

    public static bool? FromDescription(string? json, double threshold)
        => Parse(json, threshold).HighRisk;

    public static ForecastRiskParse Parse(string? json, double threshold)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return Empty;
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(json);
        }
        catch (JsonException)
        {
            return Empty;
        }

        using (document)
        {
            if (!document.RootElement.TryGetProperty("channels", out var channels)
                || channels.ValueKind != JsonValueKind.Object)
            {
                return Empty;
            }

            List<ForecastChannelValue> values = [];
            var anyHigh = false;
            foreach (var subject in channels.EnumerateObject())
            {
                if (subject.Value.ValueKind != JsonValueKind.Object)
                {
                    continue;
                }

                foreach (var category in subject.Value.EnumerateObject())
                {
                    if (category.Value.ValueKind != JsonValueKind.Object
                        || !category.Value.TryGetProperty("value", out var value)
                        || value.ValueKind != JsonValueKind.Number
                        || !value.TryGetDouble(out var number))
                    {
                        continue;
                    }

                    values.Add(new ForecastChannelValue(subject.Name, category.Name, number));
                    if (number >= threshold)
                    {
                        anyHigh = true;
                    }
                }
            }

            if (values.Count == 0)
            {
                return Empty;
            }

            return new ForecastRiskParse(anyHigh, values);
        }
    }
}
