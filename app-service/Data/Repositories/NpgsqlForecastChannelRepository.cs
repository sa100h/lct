using AppService.Models;
using AppService.Services.Domain;
using Npgsql;
using NpgsqlTypes;

namespace AppService.Data.Repositories;

public sealed class NpgsqlForecastChannelRepository(string connectionString) : IForecastChannelRepository
{
    public async Task<ForecastChannelSnapshot> GetLatestForObjectsAsync(
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

    public async Task<IReadOnlyDictionary<int, string>> GetNamesByIdsAsync(
        IReadOnlyCollection<int> channelIds,
        CancellationToken cancellationToken = default)
    {
        if (channelIds.Count == 0)
        {
            return new Dictionary<int, string>();
        }

        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "SELECT id, sensor_name FROM sensor_channels WHERE id = ANY(@ids)",
            connection);
        command.Parameters
            .Add("ids", NpgsqlDbType.Array | NpgsqlDbType.Integer)
            .Value = channelIds.ToArray();

        var names = new Dictionary<int, string>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            var name = reader.IsDBNull(1) ? null : reader.GetString(1);
            if (!string.IsNullOrWhiteSpace(name))
            {
                names[reader.GetInt32(0)] = name;
            }
        }

        return names;
    }
}
