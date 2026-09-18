namespace AppService.Services.Domain;

public static class RoleCatalog
{
    public const string Admin = "admin";
    public const string Technician = "technician";
    public const string DispatcherOds = "dispatcher_ods";
    public const string DispatcherDistrict = "dispatcher_district";

    private static readonly IReadOnlyDictionary<string, IReadOnlyList<string>> RolePermissions =
        new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
        {
            [Admin] = [PermissionCodes.DemoAccess],
            [Technician] = [PermissionCodes.DemoAccess],
            [DispatcherOds] = [PermissionCodes.DemoAccess],
            [DispatcherDistrict] = [PermissionCodes.DemoAccess]
        };

    public static IReadOnlyList<string> GetPermissions(string role) => RolePermissions[role];
}
