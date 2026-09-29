using AppService.Models;
using AppService.Services.Domain;
using Npgsql;

namespace AppService.Data.Repositories;

public sealed class NpgsqlReportFeedRepository(string connectionString) : IReportFeedRepository
{
    public async Task<int> CountAlarmsAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT COUNT(*)::int
            FROM events_log e
            WHERE e.is_alarm AND e.event_datetime >= @from AND e.event_datetime < @to
            """, connection);
        AddRange(command, fromInclusive, toExclusive);
        return (int)(await command.ExecuteScalarAsync(cancellationToken) ?? 0);
    }

    public Task<IReadOnlyDictionary<DateOnly, int>> GetAlarmCountsByMoscowDayAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default)
        => ReadMoscowDayCountsAsync("""
            SELECT (e.event_datetime AT TIME ZONE 'Europe/Moscow')::date, COUNT(*)::int
            FROM events_log e
            WHERE e.is_alarm AND e.event_datetime >= @from AND e.event_datetime < @to
            GROUP BY 1
            """, fromInclusive, toExclusive, cancellationToken);

    public async Task<IReadOnlyList<ReportStatusCount>> GetRequestCountsByStatusCreatedAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT s.name, COUNT(r.id)::int
            FROM request_statuses s
            LEFT JOIN requests r ON r.request_status_id = s.id
              AND r.created_at >= @from AND r.created_at < @to
            GROUP BY s.name
            """, connection);
        AddRange(command, fromInclusive, toExclusive);
        return await ReadStatusCountsAsync(command, cancellationToken);
    }

    public Task<IReadOnlyDictionary<DateOnly, int>> GetRequestCountsByMoscowDayAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default)
        => ReadMoscowDayCountsAsync("""
            SELECT (r.created_at AT TIME ZONE 'Europe/Moscow')::date, COUNT(*)::int
            FROM requests r
            WHERE r.created_at >= @from AND r.created_at < @to
            GROUP BY 1
            """, fromInclusive, toExclusive, cancellationToken);

    public async Task<IReadOnlyList<ReportStatusCount>> GetForecastCountsByStatusAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT CASE
                WHEN j.end_composition_time IS NOT NULL THEN 'done'
                WHEN j.start_composition_time IS NOT NULL THEN 'running'
                ELSE 'pending'
            END, COUNT(*)::int
            FROM forecast_journal j
            WHERE j.creation_time >= @from AND j.creation_time < @to
            GROUP BY 1
            """, connection);
        AddRange(command, fromInclusive, toExclusive);
        return await ReadStatusCountsAsync(command, cancellationToken);
    }

    public async Task<(int Total, IReadOnlyList<AlarmReportRow> Rows)> ListAlarmsAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        int limit,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var countCommand = new NpgsqlCommand("""
            SELECT COUNT(*)::int
            FROM events_log e
            WHERE e.is_alarm AND e.event_datetime >= @from AND e.event_datetime < @to
            """, connection);
        AddRange(countCommand, fromInclusive, toExclusive);
        var total = (int)(await countCommand.ExecuteScalarAsync(cancellationToken) ?? 0);

        await using var listCommand = new NpgsqlCommand("""
            SELECT e.event_datetime, o.dispatcher_object_name, e.sensor_channel_id, e.sensor_value
            FROM events_log e
            JOIN sensor_channels c ON c.id = e.sensor_channel_id
            JOIN dispatcher_objects o ON o.id = c.dispatcher_object_id
            WHERE e.is_alarm AND e.event_datetime >= @from AND e.event_datetime < @to
            ORDER BY e.event_datetime DESC, e.id DESC
            LIMIT @limit
            """, connection);
        AddRange(listCommand, fromInclusive, toExclusive);
        listCommand.Parameters.AddWithValue("limit", limit);

        var rows = new List<AlarmReportRow>();
        await using var reader = await listCommand.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            rows.Add(new AlarmReportRow(
                ReadUtc(reader, 0),
                reader.GetString(1),
                reader.GetInt32(2),
                reader.IsDBNull(3) ? null : reader.GetString(3)));
        }

        return (total, rows);
    }

    public async Task<(int Total, IReadOnlyList<RequestReportRow> Rows)> ListRequestsAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        int limit,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var countCommand = new NpgsqlCommand("""
            SELECT COUNT(*)::int
            FROM requests r
            WHERE r.created_at >= @from AND r.created_at < @to
            """, connection);
        AddRange(countCommand, fromInclusive, toExclusive);
        var total = (int)(await countCommand.ExecuteScalarAsync(cancellationToken) ?? 0);

        await using var listCommand = new NpgsqlCommand($"""
            SELECT r.created_at,
                   r.request_description,
                   COALESCE(o.dispatcher_object_name, ''),
                   s.name,
                   COALESCE(d.login, ''),
                   COALESCE(t.login, '')
            FROM requests r
            JOIN request_statuses s ON s.id = r.request_status_id
            LEFT JOIN users d ON d.id = r.user_dispatcher_id
            LEFT JOIN users t ON t.id = r.user_technician_id
            {NpgsqlRequestRepository.FirstObjectJoin}
            WHERE r.created_at >= @from AND r.created_at < @to
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT @limit
            """, connection);
        AddRange(listCommand, fromInclusive, toExclusive);
        listCommand.Parameters.AddWithValue("limit", limit);

        var rows = new List<RequestReportRow>();
        await using var reader = await listCommand.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            rows.Add(new RequestReportRow(
                ReadUtc(reader, 0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetString(3),
                reader.GetString(4),
                reader.GetString(5)));
        }

        return (total, rows);
    }

    public async Task<IReadOnlyList<TechnicianReportRow>> ListTechnicianLoadsAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT t.login,
              COUNT(*) FILTER (WHERE r.created_at >= @from AND r.created_at < @to)::int,
              COUNT(*) FILTER (
                WHERE s.name = 'Закрыта' AND r.updated_at >= @from AND r.updated_at < @to)::int
            FROM users t
            JOIN requests r ON r.user_technician_id = t.id
            JOIN request_statuses s ON s.id = r.request_status_id
            GROUP BY t.login
            HAVING COUNT(*) FILTER (WHERE r.created_at >= @from AND r.created_at < @to) > 0
                OR COUNT(*) FILTER (
                    WHERE s.name = 'Закрыта' AND r.updated_at >= @from AND r.updated_at < @to) > 0
            ORDER BY t.login
            """, connection);
        AddRange(command, fromInclusive, toExclusive);

        var rows = new List<TechnicianReportRow>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            rows.Add(new TechnicianReportRow(
                reader.GetString(0),
                reader.GetInt32(1),
                reader.GetInt32(2)));
        }

        return rows;
    }

    public async Task<IReadOnlyList<ForecastJournalReportRow>> ListForecastJournalsAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT j.id, j.creation_time, COALESCE(u.login, 'Автоматически'),
                   j.start_composition_time, j.end_composition_time,
                   (SELECT COUNT(DISTINCT channel.dispatcher_object_id)::int
                    FROM jsonb_object_keys(j.forecast_channels) AS key(channel_id)
                    JOIN sensor_channels channel ON channel.id = key.channel_id::int)
            FROM forecast_journal j
            LEFT JOIN users u ON u.id = j.user_created_id
            WHERE j.creation_time >= @from AND j.creation_time < @to
            ORDER BY j.creation_time DESC, j.id DESC
            """, connection);
        AddRange(command, fromInclusive, toExclusive);

        var rows = new List<ForecastJournalReportRow>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            rows.Add(new ForecastJournalReportRow(
                reader.GetGuid(0),
                ReadUtc(reader, 1),
                reader.GetString(2),
                ReadUtcOrNull(reader, 3),
                ReadUtcOrNull(reader, 4),
                reader.GetInt32(5)));
        }

        return rows;
    }

    public async Task<IReadOnlyDictionary<Guid, IReadOnlyList<ForecastJournalResult>>> ListForecastResultsByJournalsAsync(
        IReadOnlyList<Guid> ids,
        CancellationToken cancellationToken = default)
    {
        if (ids.Count == 0)
        {
            return new Dictionary<Guid, IReadOnlyList<ForecastJournalResult>>();
        }

        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT forecast_journal_id, forecast_description::text, is_erroneous
            FROM forecast_results
            WHERE forecast_journal_id = ANY(@ids)
              AND dispatcher_object_id IS NOT NULL
            """, connection);
        command.Parameters.AddWithValue("ids", ids.ToArray());

        var map = new Dictionary<Guid, List<ForecastJournalResult>>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            var journalId = reader.GetGuid(0);
            if (!map.TryGetValue(journalId, out var list))
            {
                list = [];
                map[journalId] = list;
            }

            list.Add(new ForecastJournalResult(
                reader.IsDBNull(1) ? "{}" : reader.GetString(1),
                reader.GetBoolean(2)));
        }

        return map.ToDictionary(
            pair => pair.Key,
            pair => (IReadOnlyList<ForecastJournalResult>)pair.Value);
    }

    private async Task<IReadOnlyDictionary<DateOnly, int>> ReadMoscowDayCountsAsync(
        string sql,
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(sql, connection);
        AddRange(command, fromInclusive, toExclusive);
        var result = new Dictionary<DateOnly, int>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result[DateOnly.FromDateTime(reader.GetDateTime(0))] = reader.GetInt32(1);
        }

        return result;
    }

    private static async Task<IReadOnlyList<ReportStatusCount>> ReadStatusCountsAsync(
        NpgsqlCommand command,
        CancellationToken cancellationToken)
    {
        var result = new List<ReportStatusCount>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new ReportStatusCount(reader.GetString(0), reader.GetInt32(1)));
        }

        return result;
    }

    private static void AddRange(NpgsqlCommand command, DateTimeOffset fromInclusive, DateTimeOffset toExclusive)
    {
        command.Parameters.AddWithValue("from", fromInclusive);
        command.Parameters.AddWithValue("to", toExclusive);
    }

    private static DateTimeOffset ReadUtc(NpgsqlDataReader reader, int ordinal)
    {
        var value = reader.GetDateTime(ordinal);
        return new DateTimeOffset(DateTime.SpecifyKind(value, DateTimeKind.Utc));
    }

    private static DateTimeOffset? ReadUtcOrNull(NpgsqlDataReader reader, int ordinal)
        => reader.IsDBNull(ordinal) ? null : ReadUtc(reader, ordinal);
}
