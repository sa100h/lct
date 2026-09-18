namespace AppService.Services;

internal sealed record MlPredictRequest(
    string Category,
    string SubjectId,
    Dictionary<string, double> CurrentFeatures,
    int HorizonHours);
