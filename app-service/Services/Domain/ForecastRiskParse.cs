using AppService.Models;

namespace AppService.Services.Domain;

public sealed record ForecastRiskParse(
    bool? HighRisk,
    IReadOnlyList<ForecastChannelValue> Values);
