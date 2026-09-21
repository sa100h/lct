namespace AppService.Services.Infrastructure;

public sealed class EventFeedOptions
{
    public const string SectionName = "EventFeed";

    public bool Enabled { get; init; }
    public string BaseUrl { get; init; } = "http://localhost:8081";
    public TimeSpan PollInterval { get; init; } = TimeSpan.FromMinutes(5);
    public TimeSpan Lookback { get; init; } = TimeSpan.FromMinutes(7);
    public int PageSize { get; init; } = 1000;
    public TimeSpan RequestTimeout { get; init; } = TimeSpan.FromSeconds(30);
}

