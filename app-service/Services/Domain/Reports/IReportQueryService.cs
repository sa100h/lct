using AppService.Models;

namespace AppService.Services.Domain;

public interface IReportQueryService
{
    Task<ReportDocument> BuildAsync(
        string code,
        DateOnly from,
        DateOnly to,
        CancellationToken cancellationToken = default);
}
