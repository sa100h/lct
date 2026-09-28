namespace AppService.Services.Infrastructure;

public sealed class ForecastOptions
{
    public const string SectionName = "Forecast";

    public double RiskThreshold { get; set; } = 0.5;
}
