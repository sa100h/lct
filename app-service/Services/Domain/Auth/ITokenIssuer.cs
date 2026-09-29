namespace AppService.Services.Domain;

public interface ITokenIssuer
{
    string IssueAccess(Guid userId, Guid familyId, string role, string login, DateTimeOffset now);
    string CreateRefresh();
    byte[] HashRefresh(string refreshToken);
}
