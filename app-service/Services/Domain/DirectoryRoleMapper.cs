namespace AppService.Services.Domain;

public sealed class DirectoryRoleMapper
{
    private readonly IReadOnlyDictionary<string, string> mappings;

    public DirectoryRoleMapper(AdGroupOptions options)
    {
        var groupNames = new[] { options.Admin, options.Technician, options.DispatcherOds, options.DispatcherDistrict };
        if (groupNames.Any(string.IsNullOrWhiteSpace)
            || groupNames.Distinct(StringComparer.OrdinalIgnoreCase).Count() != groupNames.Length)
            throw new InvalidOperationException("AD group names must be nonempty and distinct.");

        mappings = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            [options.Admin] = RoleCatalog.Admin,
            [options.Technician] = RoleCatalog.Technician,
            [options.DispatcherOds] = RoleCatalog.DispatcherOds,
            [options.DispatcherDistrict] = RoleCatalog.DispatcherDistrict
        };
    }

    public bool TryResolveRole(IEnumerable<string> groups, out string role)
    {
        var matched = groups.Where(mappings.ContainsKey)
            .Select(group => mappings[group]).Distinct(StringComparer.Ordinal).ToArray();
        role = matched.Length == 1 ? matched[0] : string.Empty;
        return matched.Length == 1;
    }
}
