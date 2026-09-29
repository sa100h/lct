namespace AppService.Models;

public sealed record RequestReportBody(int Total, IReadOnlyList<RequestReportRow> Rows) : IReportBody;
