using System.Text.Json;

namespace AppService.Contracts;

public sealed class MlModelStatus
{
    public string Category { get; init; } = string.Empty;
    public string State { get; init; } = string.Empty;
    public string ModelVersion { get; init; } = string.Empty;
    public DateTime? TrainedAt { get; init; }
    public Dictionary<string, JsonElement>? Metrics { get; init; }
}
