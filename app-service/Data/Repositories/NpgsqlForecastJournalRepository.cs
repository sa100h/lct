using System.Text.Json;
using AppService.Models;
using AppService.Services.Domain;
using Npgsql;
using NpgsqlTypes;

namespace AppService.Data.Repositories;

public sealed class NpgsqlForecastJournalRepository(string connectionString) : IForecastJournalRepository
{
    public async Task<IReadOnlyList<int>> FindMissingDispatcherObjectIdsAsync(
        IReadOnlyCollection<int> dispatcherObjectIds,
        CancellationToken cancellationToken = default)
    {
        if (dispatcherObjectIds.Count == 0)
        {
            return [];
        }

        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "SELECT id FROM dispatcher_objects WHERE id = ANY(@objectIds)",
            connection);
        command.Parameters
            .Add("objectIds", NpgsqlDbType.Array | NpgsqlDbType.Integer)
            .Value = dispatcherObjectIds.ToArray();

        var existingIds = new HashSet<int>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            existingIds.Add(reader.GetInt32(0));
        }

        return dispatcherObjectIds
            .Where(id => !existingIds.Contains(id))
            .OrderBy(id => id)
            .ToArray();
    }

    public async Task<ForecastJournalEntry> CreateAsync(
        Guid userId,
        string description,
        IReadOnlyDictionary<int, string> channelReadings,
        IReadOnlyList<int>? dispatcherObjectIds,
        DateTimeOffset createdAt,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            INSERT INTO forecast_journal
                (description, user_created_id, forecast_channels, creation_time, run_type)
            VALUES
                (@description, @userId, @forecastChannels, @creationTime, 'manual')
            RETURNING id
            """, connection);
        command.Parameters.AddWithValue("description", NpgsqlDbType.Text, description);
        command.Parameters.AddWithValue("userId", NpgsqlDbType.Uuid, userId);
        command.Parameters.AddWithValue(
            "forecastChannels", NpgsqlDbType.Jsonb, JsonSerializer.Serialize(channelReadings));
        command.Parameters.AddWithValue(
            "creationTime",
            NpgsqlDbType.Timestamp,
            DateTime.SpecifyKind(createdAt.UtcDateTime, DateTimeKind.Unspecified));

        var id = (Guid)(await command.ExecuteScalarAsync(cancellationToken)
            ?? throw new InvalidOperationException("Forecast journal insert did not return an id."));

        return new ForecastJournalEntry(id, createdAt, dispatcherObjectIds);
    }

    public async Task<IReadOnlyList<ForecastAuthor>> ListAuthorsAsync(
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT DISTINCT u.id, u.login
            FROM forecast_journal j
            JOIN users u ON u.id = j.user_created_id
            ORDER BY u.login
            """, connection);

        var result = new List<ForecastAuthor>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new ForecastAuthor(reader.GetGuid(0), reader.GetString(1)));
        }

        return result;
    }

    public async Task<(IReadOnlyList<ForecastHistoryListRow> Items, int Total)> ListRowsAsync(
        Guid? createdBy,
        DateOnly? from,
        DateOnly? to,
        int offset,
        int limit,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);

        const string filters = """
            FROM forecast_journal j
            LEFT JOIN users u ON u.id = j.user_created_id
            WHERE (@createdBy::uuid IS NULL OR j.user_created_id = @createdBy)
              AND (@fromDate::date IS NULL OR j.creation_time::date >= @fromDate)
              AND (@toDate::date IS NULL OR j.creation_time::date <= @toDate)
            """;

        await using var countCommand = connection.CreateCommand();
        countCommand.CommandText = $"SELECT COUNT(*)::int {filters}";
        AddListParameters(countCommand, createdBy, from, to);
        var total = (int)(await countCommand.ExecuteScalarAsync(cancellationToken)
            ?? throw new InvalidOperationException("Forecast history count returned null."));

        await using var listCommand = connection.CreateCommand();
        listCommand.CommandText = $"""
            SELECT j.id, j.creation_time, COALESCE(u.login, 'Автоматически'),
                   j.start_composition_time, j.end_composition_time,
                   (SELECT COUNT(DISTINCT channel.dispatcher_object_id)::int
                    FROM jsonb_object_keys(j.forecast_channels) AS key(channel_id)
                    JOIN sensor_channels channel ON channel.id = key.channel_id::int)
            {filters}
            ORDER BY j.creation_time DESC, j.id DESC
            OFFSET @offset LIMIT @limit
            """;
        AddListParameters(listCommand, createdBy, from, to);
        listCommand.Parameters.AddWithValue("offset", offset);
        listCommand.Parameters.AddWithValue("limit", limit);

        var items = new List<ForecastHistoryListRow>();
        await using var reader = await listCommand.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            items.Add(new ForecastHistoryListRow(
                reader.GetGuid(0),
                ReadUtc(reader, 1),
                reader.GetString(2),
                ReadUtcOrNull(reader, 3),
                ReadUtcOrNull(reader, 4),
                reader.GetInt32(5)));
        }

        return (items, total);
    }

    public async Task<ForecastHistoryHeader?> GetHeaderAsync(
        Guid id,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT j.id, j.creation_time, COALESCE(u.login, 'Автоматически'),
                   j.start_composition_time, j.end_composition_time,
                   ARRAY(SELECT DISTINCT channel.dispatcher_object_id
                         FROM jsonb_object_keys(j.forecast_channels) AS key(channel_id)
                         JOIN sensor_channels channel ON channel.id = key.channel_id::int)
            FROM forecast_journal j
            LEFT JOIN users u ON u.id = j.user_created_id
            WHERE j.id = @id
            """, connection);
        command.Parameters.AddWithValue("id", id);

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            return null;
        }

        return new ForecastHistoryHeader(
            reader.GetGuid(0),
            ReadUtc(reader, 1),
            reader.GetString(2),
            ReadUtcOrNull(reader, 3),
            ReadUtcOrNull(reader, 4),
            reader.GetFieldValue<int[]>(5));
    }

    private static void AddListParameters(
        NpgsqlCommand command,
        Guid? createdBy,
        DateOnly? from,
        DateOnly? to)
    {
        var createdByParameter = command.Parameters.Add("createdBy", NpgsqlDbType.Uuid);
        createdByParameter.Value = createdBy is null ? DBNull.Value : createdBy.Value;
        var fromParameter = command.Parameters.Add("fromDate", NpgsqlDbType.Date);
        fromParameter.Value = from is null ? DBNull.Value : from.Value;
        var toParameter = command.Parameters.Add("toDate", NpgsqlDbType.Date);
        toParameter.Value = to is null ? DBNull.Value : to.Value;
    }

    private static DateTimeOffset ReadUtc(NpgsqlDataReader reader, int ordinal)
    {
        var value = reader.GetDateTime(ordinal);
        return new DateTimeOffset(DateTime.SpecifyKind(value, DateTimeKind.Utc));
    }

    private static DateTimeOffset? ReadUtcOrNull(NpgsqlDataReader reader, int ordinal)
        => reader.IsDBNull(ordinal) ? null : ReadUtc(reader, ordinal);
}
