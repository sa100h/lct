using AppService.Models;

namespace AppService.Services.Domain;

public sealed class RoleAccessCatalog
{
    private readonly IReadOnlyDictionary<string, string> rolesByGroup;
    private readonly IReadOnlyDictionary<string, IReadOnlyList<string>> permissionsByRole;

    public IReadOnlyList<string> AllPermissions { get; }

    public RoleAccessCatalog(IEnumerable<RoleDefinition> definitions)
    {
        var entries = definitions.ToArray();
        if (entries.Length == 0)
            throw new InvalidOperationException("At least one application role must be configured.");

        var groups = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var permissions = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal);
        foreach (var definition in entries)
        {
            if (string.IsNullOrWhiteSpace(definition.Code) || definition.Code.Length > 256
                || string.IsNullOrWhiteSpace(definition.GroupDn)
                || definition.Permissions.Any(string.IsNullOrWhiteSpace)
                || definition.Permissions.Distinct(StringComparer.Ordinal).Count() != definition.Permissions.Count)
                throw new InvalidOperationException("Role definitions must have a code, a group DN and unique permissions.");

            if (!groups.TryAdd(definition.GroupDn, definition.Code)
                || !permissions.TryAdd(definition.Code, definition.Permissions.ToArray()))
                throw new InvalidOperationException("Role codes and AD group DNs must be unique.");
        }

        rolesByGroup = groups;
        permissionsByRole = permissions;
        AllPermissions = permissions.Values.SelectMany(values => values)
            .Distinct(StringComparer.Ordinal)
            .ToArray();
    }

    public bool TryResolveRole(IEnumerable<string> groupDns, out string role)
    {
        var matches = groupDns.Where(rolesByGroup.ContainsKey)
            .Select(group => rolesByGroup[group])
            .Distinct(StringComparer.Ordinal)
            .Take(2)
            .ToArray();
        role = matches.Length == 1 ? matches[0] : string.Empty;
        return matches.Length == 1;
    }

    public IReadOnlyList<string> GetPermissions(string role) => permissionsByRole[role];

    public static string ToDatabaseRoleName(string jwtRole) => jwtRole switch
    {
        "admin" => "Admins",
        "technician" => "Technics",
        "dispatcher_ods" => "Dispetchers_ODS",
        "dispatcher_district" => "Dispetchers_rayon",
        _ => throw new ArgumentException($"Unknown role '{jwtRole}'.", nameof(jwtRole)),
    };
}
