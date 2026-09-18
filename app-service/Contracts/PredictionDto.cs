namespace AppService.Contracts;

public sealed class PredictionDto
{
    public string Category { get; init; } = string.Empty;
    public string SubjectId { get; init; } = string.Empty;
    public double RiskScore { get; init; }
    public double Probability { get; init; }
    public bool PredictedLabel { get; init; }
    public int HorizonHours { get; init; }
    public DateTime PredictedAt { get; init; }
    public string ModelVersion { get; init; } = string.Empty;
    public Dictionary<string, double>? FeatureImportance { get; init; }
}
