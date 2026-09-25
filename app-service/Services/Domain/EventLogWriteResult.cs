namespace AppService.Services.Domain;

public sealed record EventLogWriteResult(
    int InsertedCount,
    int DuplicateCount,
    int UnknownEventCount,
    IReadOnlyCollection<long> UnknownChannelIds);
