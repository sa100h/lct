using AppService.Models;
using Npgsql;
using NpgsqlTypes;

namespace AppService.Data.Repositories;

internal static class ForecastChannelReadings
{
    private const string NoConnection = "Нет связи";
    private const string LatestReadingsSql = """
        WITH RECURSIVE selected_objects AS (
            SELECT id FROM dispatcher_objects WHERE id = ANY(@objectIds)
            UNION
            SELECT child.id
            FROM dispatcher_objects child
            JOIN selected_objects parent ON child.parent_id = parent.id
        )
        SELECT channel.id, latest.sensor_value
        FROM sensor_channels channel
        LEFT JOIN LATERAL (
            SELECT event.sensor_value
            FROM events_log event
            WHERE event.sensor_channel_id = channel.id
              AND event.event_datetime >= @from
              AND event.event_datetime <= @to
              AND event.sensor_value IS NOT NULL
            ORDER BY event.event_datetime DESC, event.id DESC
            LIMIT 1
        ) latest ON TRUE
        WHERE @allObjects OR channel.dispatcher_object_id IN (SELECT id FROM selected_objects)
        ORDER BY channel.id
        """;

    public static async Task<ForecastChannelSnapshot> ReadLatestAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction? transaction,
        IReadOnlyCollection<int>? dispatcherObjectIds,
        DateTimeOffset from,
        DateTimeOffset to,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(LatestReadingsSql, connection, transaction);
        command.Parameters.AddWithValue("objectIds", NpgsqlDbType.Array | NpgsqlDbType.Integer,
            dispatcherObjectIds?.ToArray() ?? []);
        command.Parameters.AddWithValue("allObjects", dispatcherObjectIds is null);
        command.Parameters.AddWithValue("from", NpgsqlDbType.TimestampTz, from.UtcDateTime);
        command.Parameters.AddWithValue("to", NpgsqlDbType.TimestampTz, to.UtcDateTime);

        var readings = new Dictionary<int, string>();
        var activeChannelIds = new List<int>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            var channelId = reader.GetInt32(0);
            if (reader.IsDBNull(1))
            {
                readings.Add(channelId, NoConnection);
            }
            else
            {
                readings.Add(channelId, reader.GetString(1));
                activeChannelIds.Add(channelId);
            }
        }
        return new ForecastChannelSnapshot(readings, activeChannelIds);
    }
}
