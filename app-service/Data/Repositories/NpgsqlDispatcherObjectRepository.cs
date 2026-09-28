using AppService.Models;
using AppService.Services.Domain;
using Npgsql;

namespace AppService.Data.Repositories;

public sealed class NpgsqlDispatcherObjectRepository(string connectionString) : IDispatcherObjectRepository
{
    public async Task<IReadOnlyList<DispatcherObjectInfo>> GetAllWithDescendantStatusesAsync(
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            WITH RECURSIVE object_tree AS (
                SELECT id AS ancestor_id, id AS descendant_id
                FROM dispatcher_objects

                UNION

                SELECT tree.ancestor_id, child.id
                FROM object_tree tree
                JOIN dispatcher_objects child ON child.parent_id = tree.descendant_id
            ),
            aggregated_statuses AS (
                SELECT
                    tree.ancestor_id,
                    COUNT(channel.id)::integer AS channel_count,
                    COALESCE(
                        ARRAY_AGG(DISTINCT status.name ORDER BY status.name)
                            FILTER (WHERE status.name IS NOT NULL),
                        ARRAY[]::text[]
                    ) AS statuses
                FROM object_tree tree
                LEFT JOIN sensor_channels channel
                    ON channel.dispatcher_object_id = tree.descendant_id
                LEFT JOIN sensor_statuses status
                    ON status.id = channel.sensor_status_id
                GROUP BY tree.ancestor_id
            ),
            own_channels AS (
                SELECT
                    channel.dispatcher_object_id AS object_id,
                    COUNT(channel.id)::integer AS own_channel_count,
                    COALESCE(
                        ARRAY_AGG(DISTINCT status.name ORDER BY status.name)
                            FILTER (WHERE status.name IS NOT NULL),
                        ARRAY[]::text[]
                    ) AS own_statuses
                FROM sensor_channels channel
                LEFT JOIN sensor_statuses status
                    ON status.id = channel.sensor_status_id
                GROUP BY channel.dispatcher_object_id
            )
            SELECT
                object.id,
                object.parent_id,
                object.dispatcher_object_name,
                object.object_type_id,
                object_type.name,
                object.longitude,
                object.latitude,
                aggregated.statuses,
                aggregated.channel_count,
                COALESCE(own.own_statuses, ARRAY[]::text[]),
                COALESCE(own.own_channel_count, 0)
            FROM dispatcher_objects object
            JOIN object_types object_type ON object_type.id = object.object_type_id
            JOIN aggregated_statuses aggregated ON aggregated.ancestor_id = object.id
            LEFT JOIN own_channels own ON own.object_id = object.id
            ORDER BY object.hierarchy_level, object.id
            """, connection);

        var result = new List<DispatcherObjectInfo>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new DispatcherObjectInfo(
                reader.GetInt32(0),
                reader.IsDBNull(1) ? null : reader.GetInt32(1),
                reader.GetString(2),
                reader.GetInt32(3),
                reader.GetString(4),
                reader.GetDouble(5),
                reader.GetDouble(6),
                reader.GetFieldValue<string[]>(7),
                reader.GetInt32(8),
                reader.GetFieldValue<string[]>(9),
                reader.GetInt32(10)));
        }

        return result;
    }

    public async Task<IReadOnlyList<int>> GetSubtreeIdsAsync(
        int rootId,
        CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            WITH RECURSIVE tree AS (
                SELECT id FROM dispatcher_objects WHERE id = @id
                UNION ALL
                SELECT child.id
                FROM dispatcher_objects child
                JOIN tree parent ON child.parent_id = parent.id
            )
            SELECT id FROM tree ORDER BY id
            """, connection);
        command.Parameters.AddWithValue("id", rootId);

        var result = new List<int>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(reader.GetInt32(0));
        }

        return result;
    }
}
