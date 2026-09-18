namespace AppService.Contracts;

/// <summary>Stored/returned prediction record.</summary>
public sealed record PredictionResponse(
    Guid Id,
    string Category,
    string SubjectId,
    double RiskScore,
    bool PredictedLabel,
    int HorizonHours,
    string ModelVersion,
    DateTime PredictedAt,
    Dictionary<string, double>? FeatureImportance);
