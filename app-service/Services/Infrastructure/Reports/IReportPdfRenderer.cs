using AppService.Models;

namespace AppService.Services.Infrastructure;

public interface IReportPdfRenderer
{
    byte[] Render(ReportDocument document);
}
