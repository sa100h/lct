namespace AppService.Services.Domain;

public static class RequestAccess
{
    public static bool SeesAll(string? jwtRole)
        => jwtRole is "admin" or "dispatcher_ods";
}
