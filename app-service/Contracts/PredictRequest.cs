namespace AppService.Contracts;

/// <summary>Request forwarded to ml-service and persisted as a prediction.</summary>
/// <param name="Category">One of: sensor-failure, fire-risk, unauthorized-access, infrastructure-wear.</param>
/// <param name="SubjectId">Forecast subject id (sensor / cell / shaft / hatch).</param>
/// <param name="CurrentFeatures">Feature vector; keys are category feature names.</param>
/// <param name="HorizonHours">Forecast horizon in hours (1..168).</param>
public sealed record PredictRequest(
    string Category,
    string SubjectId,
    Dictionary<string, double>? CurrentFeatures = null,
    int HorizonHours = 24);

