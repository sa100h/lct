namespace AppService.Models;

public sealed record AlarmReportBody(int Total, IReadOnlyList<AlarmReportRow> Rows) : IReportBody;
