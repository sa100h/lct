using System.Text.Json;
using AppService.Services.Domain;
using Npgsql;
using NpgsqlTypes;

namespace AppService.Data.Repositories;

public sealed class NpgsqlAutomaticForecastRepository(string connectionString) : IAutomaticForecastRepository
{
    public async Task<bool> RunHourlyAsync(
        DateTimeOffset scheduledHour,
        DateTimeOffset from,
        DateTimeOffset to,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        await using (var lockCommand = new NpgsqlCommand(
                         "SELECT pg_advisory_xact_lock(52776144)", connection, transaction))
        {
            await lockCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        await using (var existingCommand = new NpgsqlCommand("""
                         SELECT EXISTS (
                             SELECT 1 FROM forecast_journal
                             WHERE run_type = 'auto' AND scheduled_hour = @scheduledHour
                         )
                         """, connection, transaction))
        {
            existingCommand.Parameters.AddWithValue(
                "scheduledHour", NpgsqlDbType.TimestampTz, scheduledHour.UtcDateTime);
            if (await existingCommand.ExecuteScalarAsync(cancellationToken) is true)
            {
                await transaction.CommitAsync(cancellationToken);
                return false;
            }
        }

        var readings = await ForecastChannelReadings.ReadLatestAsync(
            connection, transaction, null, from, to, cancellationToken);
        await UpdateConnectivityAsync(connection, transaction, readings.Keys.ToArray(), cancellationToken);

        if (readings.Count == 0)
        {
            await transaction.CommitAsync(cancellationToken);
            return false;
        }

        await using (var insertCommand = new NpgsqlCommand("""
                         INSERT INTO forecast_journal
                             (description, user_created_id, forecast_channels, creation_time,
                              run_type, scheduled_hour)
                         VALUES
                             (@description, NULL, @channels, @createdAt, 'auto', @scheduledHour)
                         """, connection, transaction))
        {
            insertCommand.Parameters.AddWithValue("description", "Автоматический прогноз");
            insertCommand.Parameters.AddWithValue(
                "channels", NpgsqlDbType.Jsonb, JsonSerializer.Serialize(readings));
            insertCommand.Parameters.AddWithValue(
                "createdAt", NpgsqlDbType.Timestamp,
                DateTime.SpecifyKind(to.UtcDateTime, DateTimeKind.Unspecified));
            insertCommand.Parameters.AddWithValue(
                "scheduledHour", NpgsqlDbType.TimestampTz, scheduledHour.UtcDateTime);
            await insertCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
        return true;
    }

    private static async Task UpdateConnectivityAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        int[] activeChannelIds,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand("""
            WITH statuses AS (
                SELECT
                    (SELECT id FROM sensor_statuses WHERE name = 'Норма') AS normal_id,
                    (SELECT id FROM sensor_statuses WHERE name = 'Нет связи') AS offline_id
            )
            UPDATE sensor_channels channel
            SET sensor_status_id = CASE
                WHEN channel.id = ANY(@activeIds) THEN statuses.normal_id
                ELSE statuses.offline_id
            END
            FROM statuses
            WHERE channel.sensor_status_id IS DISTINCT FROM CASE
                WHEN channel.id = ANY(@activeIds) THEN statuses.normal_id
                ELSE statuses.offline_id
            END
            """, connection, transaction);
        command.Parameters.AddWithValue(
            "activeIds", NpgsqlDbType.Array | NpgsqlDbType.Integer, activeChannelIds);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }
}
