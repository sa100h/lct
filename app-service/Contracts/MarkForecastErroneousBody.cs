namespace AppService.Contracts;

public sealed record MarkForecastErroneousBody(IReadOnlyList<int> DispatcherObjectIds);
