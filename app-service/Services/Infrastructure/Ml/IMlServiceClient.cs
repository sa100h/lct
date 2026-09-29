using AppService.Contracts;

namespace AppService.Services;

public interface IMlServiceClient
{
    Task<PredictionDto> PredictAsync(PredictRequest request, CancellationToken cancellationToken = default);
    Task<StatusDto> GetStatusAsync(CancellationToken cancellationToken = default);
}
