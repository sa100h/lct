using System.Text.Json;
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
}
