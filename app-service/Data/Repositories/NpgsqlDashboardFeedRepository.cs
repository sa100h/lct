using AppService.Models;
using AppService.Services.Domain;
using Npgsql;

namespace AppService.Data.Repositories;

public sealed class NpgsqlDashboardFeedRepository(string connectionString) : IDashboardFeedRepository
{
    public const string RecentRequestsSql = """
        SELECT r.id,
               r.request_description,
               COALESCE(o.id, 0),
               COALESCE(o.dispatcher_object_name, ''),
               s.name
        FROM requests r
        JOIN request_statuses s ON s.id = r.request_status_id
        LEFT JOIN dispatcher_objects o
            ON o.id = CASE
                WHEN r.dispatcher_objects_id IS NULL THEN NULL
                WHEN jsonb_typeof(r.dispatcher_objects_id::jsonb) <> 'array' THEN NULL
                WHEN jsonb_typeof(r.dispatcher_objects_id::jsonb -> 0) <> 'number' THEN NULL
                ELSE (r.dispatcher_objects_id::jsonb ->> 0)::int
            END
        ORDER BY r.id
        LIMIT 20
        """;

    public async Task<IReadOnlyList<DashboardEventRow>> GetRecentEventsAsync(
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT e.id, e.event_datetime, o.id, o.dispatcher_object_name, c.sensor_name, e.is_alarm, e.sensor_value
            FROM events_log e
            JOIN sensor_channels c ON c.id = e.sensor_channel_id
            JOIN dispatcher_objects o ON o.id = c.dispatcher_object_id
            ORDER BY e.event_datetime DESC, e.id DESC
            LIMIT 20
            """, connection);

        var result = new List<DashboardEventRow>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new DashboardEventRow(
                reader.GetInt64(0),
                ReadUtc(reader, 1),
                reader.GetInt32(2),
                reader.GetString(3),
                reader.GetString(4),
                reader.GetBoolean(5),
                reader.IsDBNull(6) ? null : reader.GetString(6)));
        }

        return result;
    }

    public async Task<IReadOnlyList<DashboardForecastRow>> GetRecentForecastsAsync(
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT id, creation_time, start_composition_time, end_composition_time
            FROM forecast_journal
            ORDER BY creation_time DESC
            LIMIT 10
            """, connection);

        var result = new List<DashboardForecastRow>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new DashboardForecastRow(
                reader.GetGuid(0),
                ReadUtc(reader, 1),
                ReadUtcOrNull(reader, 2),
                ReadUtcOrNull(reader, 3)));
        }

        return result;
    }

    public async Task<IReadOnlyList<DashboardRequestRow>> GetRecentRequestsAsync(
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(RecentRequestsSql, connection);

        var result = new List<DashboardRequestRow>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new DashboardRequestRow(
                reader.GetGuid(0),
                reader.GetString(1),
                reader.GetInt32(2),
                reader.GetString(3),
                reader.GetString(4)));
        }

        return result;
    }

    private static DateTimeOffset ReadUtc(NpgsqlDataReader reader, int ordinal)
    {
        var value = reader.GetDateTime(ordinal);
        return new DateTimeOffset(DateTime.SpecifyKind(value, DateTimeKind.Utc));
    }

    private static DateTimeOffset? ReadUtcOrNull(NpgsqlDataReader reader, int ordinal)
        => reader.IsDBNull(ordinal) ? null : ReadUtc(reader, ordinal);
}
