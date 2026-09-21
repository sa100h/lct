using System.Net.Http.Json;
using System.Text.Json;
using AppService.Contracts;
using AppService.Services.Domain;

namespace AppService.Services.Infrastructure;

public sealed class TestEventFeedClient(HttpClient http, EventFeedOptions options) : IEventFeedClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public async Task<EventFeedPageDto> GetEventsAsync(
        DateTimeOffset from,
        DateTimeOffset to,
        string? cursor,
        CancellationToken cancellationToken = default)
    {
        var query = new List<string>
        {
            $"from={Uri.EscapeDataString(from.UtcDateTime.ToString("O"))}",
            $"to={Uri.EscapeDataString(to.UtcDateTime.ToString("O"))}",
            $"limit={options.PageSize}",
        };
        if (!string.IsNullOrWhiteSpace(cursor))
        {
            query.Add($"cursor={Uri.EscapeDataString(cursor)}");
        }

        using var response = await http.GetAsync($"/api/v1/events?{string.Join('&', query)}", cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            throw new HttpRequestException(
                $"test-event-feeder failed ({(int)response.StatusCode}): {body}",
                inner: null,
                response.StatusCode);
        }

        return await response.Content.ReadFromJsonAsync<EventFeedPageDto>(JsonOptions, cancellationToken)
            ?? throw new InvalidOperationException("test-event-feeder returned an empty body.");
    }
}

