using AppService.Models;
using AppService.Services.Domain;
using Npgsql;
using NpgsqlTypes;

namespace AppService.Data.Repositories;

public sealed class NpgsqlEventLogRepository(string connectionString) : IEventLogRepository
{
    public async Task<EventLogWriteResult> InsertAsync(
        IReadOnlyCollection<EventLogEntry> events,
        CancellationToken cancellationToken = default)
    {
        if (events.Count == 0)
        {
            return new EventLogWriteResult(0, 0, 0, []);
        }

        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        var requestedChannelIds = events
            .Select(item => item.SensorChannelId)
            .Distinct()
            .ToArray();
        var databaseChannelIds = requestedChannelIds
            .Where(id => id is >= int.MinValue and <= int.MaxValue)
            .Select(id => (int)id)
            .ToArray();
        var knownChannelIds = new HashSet<long>();

        if (databaseChannelIds.Length > 0)
        {
            await using var channelCommand = new NpgsqlCommand(
                "SELECT id FROM sensor_channels WHERE id = ANY(@channelIds)",
                connection,
                transaction);
            channelCommand.Parameters
                .Add("channelIds", NpgsqlDbType.Array | NpgsqlDbType.Integer)
                .Value = databaseChannelIds;

            await using var reader = await channelCommand.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                knownChannelIds.Add(reader.GetInt32(0));
            }
        }

        var unknownChannelIds = requestedChannelIds
            .Where(id => !knownChannelIds.Contains(id))
            .OrderBy(id => id)
            .ToArray();
        var knownEvents = events
            .Where(item => knownChannelIds.Contains(item.SensorChannelId))
            .ToArray();
        var insertedCount = 0;

        if (knownEvents.Length > 0)
        {
            await using var insertCommand = new NpgsqlCommand("""
                INSERT INTO events_log (id, sensor_channel_id, event_datetime, is_alarm, sensor_value)
                SELECT *
                FROM unnest(
                    @ids::bigint[],
                    @channelIds::integer[],
                    @occurredAt::timestamptz[],
                    @isAlarm::boolean[],
                    @sensorValues::text[])
                ON CONFLICT (id) DO NOTHING
                """, connection, transaction);
            insertCommand.Parameters.Add("ids", NpgsqlDbType.Array | NpgsqlDbType.Bigint).Value =
                knownEvents.Select(item => item.Id).ToArray();
            insertCommand.Parameters.Add("channelIds", NpgsqlDbType.Array | NpgsqlDbType.Integer).Value =
                knownEvents.Select(item => checked((int)item.SensorChannelId)).ToArray();
            insertCommand.Parameters.Add("occurredAt", NpgsqlDbType.Array | NpgsqlDbType.TimestampTz).Value =
                knownEvents.Select(item => item.OccurredAt.UtcDateTime).ToArray();
            insertCommand.Parameters.Add("isAlarm", NpgsqlDbType.Array | NpgsqlDbType.Boolean).Value =
                knownEvents.Select(item => item.IsAlarm).ToArray();
            insertCommand.Parameters.Add("sensorValues", NpgsqlDbType.Array | NpgsqlDbType.Text).Value =
                knownEvents.Select(item => item.SensorValue).ToArray();

            insertedCount = await insertCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);

        return new EventLogWriteResult(
            insertedCount,
            knownEvents.Length - insertedCount,
            events.Count - knownEvents.Length,
            unknownChannelIds);
    }
}
