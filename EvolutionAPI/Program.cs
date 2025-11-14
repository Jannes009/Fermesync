using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using System.Text.Json.Serialization;

var builder = WebApplication.CreateBuilder(args);

// Add controller support with JSON serializer options
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        // Allow binding to properties with different casing
        options.JsonSerializerOptions.PropertyNameCaseInsensitive = true;
        options.JsonSerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
        options.JsonSerializerOptions.WriteIndented = true;
    });

var app = builder.Build();

app.MapControllers(); // Map all controllers

app.Run();
