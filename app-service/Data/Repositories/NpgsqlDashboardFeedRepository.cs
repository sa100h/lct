using AppService.Models;
using AppService.Services.Domain;
using Npgsql;

namespace AppService.Data.Repositories;

public sealed class NpgsqlDashboardFeedRepository(string connectionString) : IDashboardFeedRepository
{
    public async Task<IReadOnlyDictionary<DateOnly, int>> GetAlarmCountsByDayAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default)
        => await ReadDayCountsAsync("""
            SELECT (e.event_datetime AT TIME ZONE 'UTC')::date, COUNT(*)::int
            FROM events_log e
            WHERE e.is_alarm AND e.event_datetime >= @from AND e.event_datetime < @to
            GROUP BY 1
            """, fromInclusive, toExclusive, cancellationToken);

    public async Task<IReadOnlyList<DashboardStatusCount>> GetRequestCountsByStatusAsync(
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT s.name, COUNT(r.id)::int
            FROM request_statuses s
            LEFT JOIN requests r ON r.request_status_id = s.id
            GROUP BY s.name
            """, connection);
        return await ReadStatusCountsAsync(command, cancellationToken);
    }

    public async Task<IReadOnlyDictionary<DateOnly, int>> GetRequestCountsByDayAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default)
        => await ReadDayCountsAsync("""
            SELECT (r.created_at AT TIME ZONE 'UTC')::date, COUNT(*)::int
            FROM requests r
            WHERE r.created_at >= @from AND r.created_at < @to
            GROUP BY 1
            """, fromInclusive, toExclusive, cancellationToken);

    public async Task<IReadOnlyList<DashboardStatusCount>> GetForecastCountsByStatusAsync(
        DateTimeOffset fromInclusive,
        DateTimeOffset toExclusive,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT j.status, COUNT(*)::int
            FROM forecast_journal j
            WHERE j.creation_time >= @from AND j.creation_time < @to
            GROUP BY 1
            """, connection);
        AddRange(command, fromInclusive, toExclusive);
        return await ReadStatusCountsAsync(command, cancellationToken);
    }

    private async Task<IReadOnlyDictionary<DateOnly, int>> ReadDayCountsAsync(
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

    private static async Task<IReadOnlyList<DashboardStatusCount>> ReadStatusCountsAsync(
        NpgsqlCommand command,
        CancellationToken cancellationToken)
    {
        var result = new List<DashboardStatusCount>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new DashboardStatusCount(reader.GetString(0), reader.GetInt32(1)));
        }

        return result;
    }

    private static void AddRange(NpgsqlCommand command, DateTimeOffset fromInclusive, DateTimeOffset toExclusive)
    {
        command.Parameters.AddWithValue("from", fromInclusive);
        command.Parameters.AddWithValue("to", toExclusive);
    }
}
