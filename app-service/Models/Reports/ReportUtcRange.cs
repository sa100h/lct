namespace AppService.Models;

public sealed record ReportUtcRange(DateTimeOffset FromInclusive, DateTimeOffset ToExclusive);
