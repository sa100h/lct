using System.Net;
using System.Text.Json;
using AppService.Contracts;
using AppService.Services;
using Xunit;

namespace AppService.Tests;

public sealed class MlServiceClientTests
{
    [Fact]
    public async Task Predict_UsesFastApiWireFormat()
    {
        string? requestBody = null;
        using var http = new HttpClient(new StubHandler(async request =>
        {
            requestBody = await request.Content!.ReadAsStringAsync();
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("""
                    {"category":"fire-risk","subject_id":"sensor-1","risk_score":0.8,"probability":0.75,"predicted_label":true,"horizon_hours":24,"predicted_at":"2026-09-16T00:00:00Z","model_version":"v1","feature_importance":{"temperature":0.4}}
                    """),
            };
        })) { BaseAddress = new Uri("http://localhost:8000") };

        var result = await new MlServiceClient(http).PredictAsync(
            new PredictRequest("fire-risk", "sensor-1"), TestContext.Current.CancellationToken);

        using var requestJson = JsonDocument.Parse(requestBody!);
        Assert.Equal("sensor-1", requestJson.RootElement.GetProperty("subject_id").GetString());
        Assert.Equal(24, requestJson.RootElement.GetProperty("horizon_hours").GetInt32());
        Assert.Equal(JsonValueKind.Object, requestJson.RootElement.GetProperty("current_features").ValueKind);
        Assert.Equal("sensor-1", result.SubjectId);
        Assert.Equal(0.8, result.RiskScore);
        Assert.True(result.PredictedLabel);
        Assert.Equal("v1", result.ModelVersion);
        Assert.Equal(0.4, result.FeatureImportance!["temperature"]);
    }

    [Fact]
    public async Task Status_AcceptsMixedModelMetrics()
    {
        using var http = new HttpClient(new StubHandler(_ => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent("""
                {"service":"ml-service","state":"ready","models":{"fire-risk":{"category":"fire-risk","state":"trained","model_version":"v1","metrics":{"source":"synthetic-baseline","n_samples":2000}}},"now":"2026-09-16T00:00:00Z"}
                """),
        }))) { BaseAddress = new Uri("http://localhost:8000") };

        var result = await new MlServiceClient(http).GetStatusAsync(TestContext.Current.CancellationToken);

        Assert.Equal("trained", result.Models!["fire-risk"].State);
        Assert.Equal("synthetic-baseline", result.Models["fire-risk"].Metrics!["source"].GetString());
        Assert.Equal(2000, result.Models["fire-risk"].Metrics!["n_samples"].GetInt32());
    }

    private sealed class StubHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> handler) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => handler(request);
    }
}
