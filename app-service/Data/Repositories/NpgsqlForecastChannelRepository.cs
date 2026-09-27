using AppService.Services.Domain;
using Npgsql;

namespace AppService.Data.Repositories;

public sealed class NpgsqlForecastChannelRepository(string connectionString) : IForecastChannelRepository
{
    public async Task<IReadOnlyDictionary<int, string>> GetLatestForObjectsAsync(
        IReadOnlyCollection<int>? dispatcherObjectIds,
        DateTimeOffset from,
        DateTimeOffset to,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        return await ForecastChannelReadings.ReadLatestAsync(
            connection, null, dispatcherObjectIds, from, to, cancellationToken);
    }
}
