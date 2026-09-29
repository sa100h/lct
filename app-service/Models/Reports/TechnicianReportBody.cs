namespace AppService.Models;

public sealed record TechnicianReportBody(IReadOnlyList<TechnicianReportRow> Rows) : IReportBody;
