namespace AppService.Services.Infrastructure;

public sealed class ForecastOptions
{
    public const string SectionName = "Forecast";

    public double RiskThreshold { get; set; } = 0.5;

    public Dictionary<string, double> RiskThresholds { get; set; } = new(StringComparer.Ordinal);

    public double ThresholdFor(string category)
    {
        if (category is not null
            && RiskThresholds is not null
            && RiskThresholds.TryGetValue(category, out var value))
        {
            return value;
        }

        return RiskThreshold;
    }
}
