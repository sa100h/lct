namespace AppService.Contracts;

public sealed class StatusDto
{
    public string Service { get; init; } = string.Empty;
    public string State { get; init; } = string.Empty;
    public Dictionary<string, MlModelStatus>? Models { get; init; }
    public DateTime Now { get; init; }
}
