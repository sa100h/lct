namespace AppService.Contracts;

/// <summary>
/// Starts a forecast journal entry for the selected dispatcher objects.
/// A null object list means that every dispatcher object is included.
/// </summary>
public sealed record RunForecastRequest(IReadOnlyCollection<int>? DispatcherObjectIds);
