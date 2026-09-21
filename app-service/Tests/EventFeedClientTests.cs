using System.Net;
using AppService.Services.Infrastructure;
using Xunit;

namespace AppService.Tests;

public sealed class EventFeedClientTests
{
    [Fact]
    public async Task GetEvents_UsesWindowPaginationAndDeserializesLongIds()
    {
        Uri? requestedUri = null;
        using var http = new HttpClient(new StubHandler(request =>
        {
            requestedUri = request.RequestUri;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("""
                    {
                      "from":"2026-09-21T12:00:00Z",
                      "to":"2026-09-21T12:07:00Z",
                      "items":[{
                        "id":4524058421,
                        "channelId":196727,
                        "occurredAt":"2026-09-21T12:01:00Z",
                        "sourceOccurredAt":"2026-01-01T00:01:00+03:00",
                        "isAlarm":false,
                        "value":"0.01"
                      }],
                      "hasMore":true,
                      "nextCursor":"next page"
                    }
                    """),
            });
        })) { BaseAddress = new Uri("http://feed:8000") };
        var options = new EventFeedOptions { PageSize = 250 };
        var client = new TestEventFeedClient(http, options);

        var result = await client.GetEventsAsync(
            DateTimeOffset.Parse("2026-09-21T12:00:00Z"),
            DateTimeOffset.Parse("2026-09-21T12:07:00Z"),
            "previous page",
            TestContext.Current.CancellationToken);

        Assert.Contains("limit=250", requestedUri!.Query);
        Assert.Contains("cursor=previous%20page", requestedUri.Query);
        Assert.Equal(4_524_058_421, result.Items.Single().Id);
        Assert.Equal("next page", result.NextCursor);
        Assert.True(result.HasMore);
    }

    private sealed class StubHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> handler) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken) => handler(request);
    }
}
