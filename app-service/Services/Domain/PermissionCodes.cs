namespace AppService.Services.Domain;

public static class PermissionCodes
{
    // Endpoint policy name. Role assignments live in appsettings.json.
    public const string DemoAccess = "demo.access";
    public const string ModuleDashboard = "module.dashboard";
    public const string ModuleMap = "module.map";
    public const string ModulePrediction = "module.prediction";
    public const string ModuleHistory = "module.history";
    public const string ModuleNotifications = "module.notifications";
    public const string ModuleReports = "module.reports";
    public const string ModuleSettings = "module.settings";
}
