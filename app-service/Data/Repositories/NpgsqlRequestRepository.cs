using System.Text.Json;
using AppService.Models;
using AppService.Services.Domain;
using Npgsql;
using NpgsqlTypes;

namespace AppService.Data.Repositories;

public sealed class NpgsqlRequestRepository(string connectionString) : IRequestRepository
{
    private static readonly Guid NewStatusId = Guid.Parse("00000000-0000-0000-0000-000000000001");

    public async Task<bool> ForecastJournalExistsAsync(
        Guid id,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "SELECT EXISTS (SELECT 1 FROM forecast_journal WHERE id = @id)",
            connection);
        command.Parameters.AddWithValue("id", id);
        var result = await command.ExecuteScalarAsync(cancellationToken);
        return result is true;
    }

    public async Task<bool> IsActiveTechnicianAsync(
        Guid userId,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT EXISTS (
                SELECT 1 FROM users u
                JOIN roles r ON r.id = u.role_id
                WHERE u.id = @id AND u.is_active AND r.name = 'Technics')
            """, connection);
        command.Parameters.AddWithValue("id", userId);
        var result = await command.ExecuteScalarAsync(cancellationToken);
        return result is true;
    }

    public async Task<Guid> InsertAsync(
        Guid forecastJournalId,
        string description,
        Guid dispatcherUserId,
        Guid technicianId,
        IReadOnlyList<int> objectIds,
        int? priority,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            INSERT INTO requests (
                forecast_journal_id, request_description, user_dispatcher_id, user_technician_id,
                dispatcher_objects_id, execution_description, request_status_id, priority, forecast_id)
            VALUES (
                @journal, @description, @dispatcher, @technician,
                @objectIds, NULL, @status, @priority, NULL)
            RETURNING id
            """, connection);
        command.Parameters.AddWithValue("journal", forecastJournalId);
        command.Parameters.AddWithValue("description", description);
        command.Parameters.AddWithValue("dispatcher", dispatcherUserId);
        command.Parameters.AddWithValue("technician", technicianId);
        command.Parameters.AddWithValue("objectIds", NpgsqlDbType.Json, JsonSerializer.Serialize(objectIds));
        command.Parameters.AddWithValue("status", NewStatusId);
        command.Parameters.AddWithValue("priority", priority is null ? DBNull.Value : priority.Value);

        var id = await command.ExecuteScalarAsync(cancellationToken)
            ?? throw new InvalidOperationException("Request insert did not return an id.");
        return (Guid)id;
    }

    public const string FirstObjectJoin = """
        LEFT JOIN dispatcher_objects o
            ON o.id = CASE
                WHEN r.dispatcher_objects_id IS NULL THEN NULL
                WHEN jsonb_typeof(r.dispatcher_objects_id::jsonb) <> 'array' THEN NULL
                WHEN jsonb_typeof(r.dispatcher_objects_id::jsonb -> 0) <> 'number' THEN NULL
                ELSE (r.dispatcher_objects_id::jsonb ->> 0)::int
            END
        """;

    public async Task<(IReadOnlyList<RequestListItem> Items, int Total)> ListAsync(
        Guid? restrictToUserId,
        int offset,
        int limit,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);

        await using var countCommand = new NpgsqlCommand($"""
            SELECT COUNT(*)::int
            FROM requests r
            WHERE {VisibilitySql}
            """, connection);
        AddVisibility(countCommand, restrictToUserId);
        var total = (int)(await countCommand.ExecuteScalarAsync(cancellationToken) ?? 0);

        await using var listCommand = new NpgsqlCommand($"""
            SELECT r.id,
                   r.created_at,
                   r.request_description,
                   COALESCE(o.id, 0),
                   COALESCE(o.dispatcher_object_name, ''),
                   s.name,
                   COALESCE(d.login, ''),
                   COALESCE(t.login, '')
            FROM requests r
            JOIN request_statuses s ON s.id = r.request_status_id
            LEFT JOIN users d ON d.id = r.user_dispatcher_id
            LEFT JOIN users t ON t.id = r.user_technician_id
            {FirstObjectJoin}
            WHERE {VisibilitySql}
            ORDER BY r.created_at DESC, r.id DESC
            OFFSET @offset LIMIT @limit
            """, connection);
        AddVisibility(listCommand, restrictToUserId);
        listCommand.Parameters.AddWithValue("offset", offset);
        listCommand.Parameters.AddWithValue("limit", limit);

        var items = new List<RequestListItem>();
        await using var reader = await listCommand.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            items.Add(new RequestListItem(
                reader.GetGuid(0),
                ReadUtc(reader, 1),
                reader.GetString(2),
                reader.GetInt32(3),
                reader.GetString(4),
                reader.GetString(5),
                reader.GetString(6),
                reader.GetString(7)));
        }

        return (items, total);
    }

    public async Task<RequestHeader?> GetHeaderAsync(
        Guid id,
        Guid? restrictToUserId,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand($"""
            SELECT r.id,
                   r.created_at,
                   r.request_description,
                   s.name,
                   COALESCE(d.login, ''),
                   COALESCE(t.login, ''),
                   r.priority,
                   COALESCE(o.id, 0),
                   COALESCE(o.dispatcher_object_name, ''),
                   r.dispatcher_objects_id::text
            FROM requests r
            JOIN request_statuses s ON s.id = r.request_status_id
            LEFT JOIN users d ON d.id = r.user_dispatcher_id
            LEFT JOIN users t ON t.id = r.user_technician_id
            {FirstObjectJoin}
            WHERE r.id = @id AND {VisibilitySql}
            """, connection);
        command.Parameters.AddWithValue("id", id);
        AddVisibility(command, restrictToUserId);

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            return null;
        }

        return new RequestHeader(
            reader.GetGuid(0),
            ReadUtc(reader, 1),
            reader.GetString(2),
            reader.GetString(3),
            reader.GetString(4),
            reader.GetString(5),
            reader.IsDBNull(6) ? null : reader.GetInt32(6),
            reader.GetInt32(7),
            reader.GetString(8),
            ParseObjectIds(reader.IsDBNull(9) ? null : reader.GetString(9)));
    }

    public async Task<bool> StatusExistsAsync(
        string name,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "SELECT EXISTS (SELECT 1 FROM request_statuses WHERE name = @name)",
            connection);
        command.Parameters.AddWithValue("name", name);
        var result = await command.ExecuteScalarAsync(cancellationToken);
        return result is true;
    }

    public async Task<bool> UpdateStatusAsync(
        Guid id,
        string statusName,
        Guid? restrictToUserId,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(UpdateStatusSql, connection);
        command.Parameters.AddWithValue("id", id);
        command.Parameters.AddWithValue("name", statusName);
        AddVisibility(command, restrictToUserId);
        var affected = await command.ExecuteNonQueryAsync(cancellationToken);
        return affected > 0;
    }

    public const string UpdateStatusSql = """
        UPDATE requests r
        SET request_status_id = (SELECT id FROM request_statuses WHERE name = @name),
            updated_at = now()
        WHERE id = @id AND (@all OR r.user_dispatcher_id = @user OR r.user_technician_id = @user)
        """;

    private const string VisibilitySql =
        "(@all OR r.user_dispatcher_id = @user OR r.user_technician_id = @user)";

    private static void AddVisibility(NpgsqlCommand command, Guid? restrictToUserId)
    {
        command.Parameters.AddWithValue("all", restrictToUserId is null);
        command.Parameters.AddWithValue("user", restrictToUserId ?? Guid.Empty);
    }

    private static IReadOnlyList<int> ParseObjectIds(string? json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return [];
        }

        try
        {
            return JsonSerializer.Deserialize<int[]>(json) ?? [];
        }
        catch (JsonException)
        {
            return [];
        }
    }

    private static DateTimeOffset ReadUtc(NpgsqlDataReader reader, int ordinal)
    {
        var value = reader.GetDateTime(ordinal);
        return new DateTimeOffset(DateTime.SpecifyKind(value, DateTimeKind.Utc));
    }
}
