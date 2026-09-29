namespace AppService.Models;

public sealed record ReportDocument(ReportHeader Header, IReportBody Body);
