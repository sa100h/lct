using AppService.Models;

namespace AppService.Services.Domain;

public interface IDashboardQueryService
{
    Task<DashboardSnapshot> GetAsync(CancellationToken cancellationToken = default);
}
