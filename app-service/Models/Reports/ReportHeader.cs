namespace AppService.Models;

public sealed record ReportHeader(
    string Title,
    DateOnly From,
    DateOnly To,
    DateTimeOffset GeneratedAt,
    string FileName);
