using System.Net.Http.Json;
using AppService.Contracts;

namespace AppService.Ml;

/// <summary>
/// Thin HTTP client for the ml-service (FastAPI). Kept transport-agnostic so it
/// can be pointed at http://ml-service:8000 in Docker and http://localhost:8000
/// for local dev via the "MlService" config section.
/// </summary>
public sealed class MlServiceClient(HttpClient http)
{
    private static readonly string[] KnownCategories =
    {
        "sensor-failure",
        "fire-risk",
        "unauthorized-access",
        "infrastructure-wear",
    };

    public async Task<PredictionDto> PredictAsync(PredictRequest request, CancellationToken ct = default)
    {
        if (request is null) throw new ArgumentNullException(nameof(request));
        if (string.IsNullOrWhiteSpace(request.Category) || !KnownCategories.Contains(request.Category))
        {
            throw new ArgumentException(
                $"Unknown category '{request.Category}'. Expected one of: {string.Join(", ", KnownCategories)}.");
        }

        var payload = new MlPredictRequest(request.Category, request.SubjectId, request.CurrentFeatures, request.HorizonHours);
        var response = await http.PostAsJsonAsync("/predict", payload, ct);

        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(ct);
            throw new HttpRequestException($"ml-service /predict failed ({(int)response.StatusCode}): {body}");
        }

        return await response.Content.ReadFromJsonAsync<MlPredictResponse>(cancellationToken: ct)
               ?? throw new InvalidOperationException("ml-service returned an empty body.");
    }

    public async Task<StatusDto> GetStatusAsync(CancellationToken ct = default)
    {
        var response = await http.GetAsync("/status", ct);
        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException($"ml-service /status failed ({(int)response.StatusCode}).");
        }
        return await response.Content.ReadFromJsonAsync<StatusDto>(cancellationToken: ct)
               ?? throw new InvalidOperationException("ml-service /status returned an empty body.");
    }
}

// Wire-format DTOs (camelCase via JSON serializer defaults).
internal sealed record MlPredictRequest(
    string Category,
    string SubjectId,
    Dictionary<string, double>? CurrentFeatures,
    int HorizonHours);

public sealed class MlPredictResponse
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

public sealed class StatusDto
{
    public string Service { get; init; } = string.Empty;
    public string State { get; init; } = string.Empty;
    public Dictionary<string, MlModelStatus>? Models { get; init; }
    public DateTime Now { get; init; }
}

/// <summary>Alias used by the predict endpoint (ml-service response shape).</summary>
public sealed class PredictionDto : MlPredictResponse;

public sealed class MlModelStatus
{
    public string Category { get; init; } = string.Empty;
    public string State { get; init; } = string.Empty;
    public string ModelVersion { get; init; } = string.Empty;
    public DateTime? TrainedAt { get; init; }
    public Dictionary<string, double>? Metrics { get; init; }
}
