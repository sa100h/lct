using System.Text.Json;

namespace AppService.Services.Domain;

public static class ForecastRisk
{
    public static bool? FromDescription(string? json, double threshold)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return null;
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(json);
        }
        catch (JsonException)
        {
            return null;
        }

        using (document)
        {
            if (!document.RootElement.TryGetProperty("channels", out var channels)
                || channels.ValueKind != JsonValueKind.Object)
            {
                return null;
            }

            var found = false;
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

                    found = true;
                    if (number >= threshold)
                    {
                        anyHigh = true;
                    }
                }
            }

            if (!found)
            {
                return null;
            }

            return anyHigh;
        }
    }
}
