namespace AppService.Services.Domain;

// The future handler receives the loaded domain resource. Its concrete type and
// district association will be defined with the district data model.
public interface IDistrictResourceAccess<in TResource> where TResource : class
{
    Task<bool> CanAccessAsync(Guid userId, TResource resource, CancellationToken cancellationToken);
}
