namespace AppService.Services.Domain;

public sealed class AdGroupOptions
{
    public string Admin { get; set; } = string.Empty;
    public string Technician { get; set; } = string.Empty;
    public string DispatcherOds { get; set; } = string.Empty;
    public string DispatcherDistrict { get; set; } = string.Empty;
}
