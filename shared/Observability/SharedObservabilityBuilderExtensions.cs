using System.Diagnostics;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using OpenTelemetry.Exporter;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using Prometheus;
using Serilog;
using Serilog.Events;
using Serilog.Formatting.Compact;

namespace Shared.Observability;

public static class SharedObservabilityBuilderExtensions
{
    private const string HealthPath = "/health";
    private const string HealthMetricsPath = "/healthmetrics";
    private const string MetricsPath = "/metrics";

    public static WebApplicationBuilder AddSharedObservability(this WebApplicationBuilder builder, string serviceName)
    {
        var options = builder.Configuration.GetSection("Observability").Get<ObservabilityOptions>()
            ?? new ObservabilityOptions();

        Metrics.DefaultRegistry.SetStaticLabels(new Dictionary<string, string>
        {
            ["deployment_environment"] = builder.Environment.EnvironmentName,
            ["service_name"] = serviceName,
            ["service_namespace"] = options.ServiceNamespace
        });

        builder.Services.AddHealthChecks();
        builder.Services.AddSerilog((_, configuration) => configuration
            .MinimumLevel.Is(ParseLevel(options.DefaultLogLevel, LogEventLevel.Information))
            .MinimumLevel.Override("Microsoft", ParseLevel(options.FrameworkLogLevel, LogEventLevel.Warning))
            .MinimumLevel.Override("System", ParseLevel(options.FrameworkLogLevel, LogEventLevel.Warning))
            .Enrich.FromLogContext()
            .Enrich.With(new TraceContextEnricher())
            .Enrich.WithProperty("service_name", serviceName)
            .Enrich.WithProperty("service_namespace", options.ServiceNamespace)
            .Enrich.WithProperty("deployment_environment", builder.Environment.EnvironmentName)
            .WriteTo.Console(new RenderedCompactJsonFormatter()));

        var telemetry = builder.Services.AddOpenTelemetry().ConfigureResource(resource => resource
            .AddService(serviceName, serviceNamespace: options.ServiceNamespace)
            .AddAttributes([new KeyValuePair<string, object>("deployment.environment", builder.Environment.EnvironmentName)]));

        telemetry.WithTracing(tracing =>
        {
            tracing.SetSampler(new AlwaysOnSampler());
            if (options.EnableAspNetCoreTracing)
            {
                tracing.AddAspNetCoreInstrumentation(instrumentation => instrumentation.RecordException = true);
            }

            if (options.EnableHttpClientTracing)
            {
                tracing.AddHttpClientInstrumentation(instrumentation => instrumentation.RecordException = true);
            }

            if (options.EnableEntityFrameworkCoreTracing)
            {
                tracing.AddEntityFrameworkCoreInstrumentation();
            }

            if (Uri.TryCreate(options.OtlpEndpoint, UriKind.Absolute, out var endpoint))
            {
                tracing.AddOtlpExporter(exporter =>
                {
                    exporter.Endpoint = endpoint;
                    exporter.Protocol = OtlpExportProtocol.Grpc;
                });
            }
        });

        return builder;
    }

    public static WebApplication UseSharedObservability(this WebApplication app)
    {
        app.UseHttpMetrics(options => options.ReduceStatusCodeCardinality());
        app.UseHealthChecksPrometheusExporter(HealthMetricsPath);
        app.UseSerilogRequestLogging(options => options.EnrichDiagnosticContext = (context, httpContext) =>
        {
            context.Set("request_host", httpContext.Request.Host.Value);
            if (Activity.Current is not null)
            {
                context.Set("trace_id", Activity.Current.TraceId.ToHexString());
                context.Set("span_id", Activity.Current.SpanId.ToHexString());
            }
        });
        app.MapHealthChecks(HealthPath).AllowAnonymous();
        app.MapMetrics(MetricsPath).AllowAnonymous();
        return app;
    }

    private static LogEventLevel ParseLevel(string configured, LogEventLevel fallback) =>
        Enum.TryParse<LogEventLevel>(configured, true, out var level) ? level : fallback;
}

