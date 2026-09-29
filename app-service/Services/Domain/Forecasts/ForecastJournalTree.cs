using AppService.Models;

namespace AppService.Services.Domain;

public static class ForecastJournalTree
{
    public static HashSet<int> AllowedIds(
        IReadOnlyList<int>? channelObjectIds,
        IReadOnlyList<DispatcherObjectInfo> all)
    {
        var byId = all.ToDictionary(item => item.Id);
        var includedIds = new HashSet<int>();
        foreach (var objectId in channelObjectIds ?? [])
        {
            int? currentId = objectId;
            while (currentId is int ancestorId && byId.TryGetValue(ancestorId, out var current)
                   && includedIds.Add(ancestorId))
            {
                currentId = current.ParentId;
            }
        }

        return includedIds;
    }
}
