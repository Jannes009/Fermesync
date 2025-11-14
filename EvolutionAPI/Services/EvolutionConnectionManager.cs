using Pastel.Evolution;
using System;

namespace EvolutionAPI.Services
{
    public static class EvolutionConnectionManager
    {
        private const string DefaultLicenseAccount = "DE12111082";
        private const string DefaultLicensePin = "9824607";
        private const string DefaultCommonDatabase = "SageCommon";

        public static void EnsureConnection(
            string serverName,
            string databaseName,
            string username,
            string password,
            string? commonDatabaseName = null)
        {
            ValidateRequired("serverName", serverName);
            ValidateRequired("databaseName", databaseName);
            ValidateRequired("username", username);
            ValidateRequired("password", password);

            var commonDb = string.IsNullOrWhiteSpace(commonDatabaseName)
                ? DefaultCommonDatabase
                : commonDatabaseName;

            DatabaseContext.CreateCommonDBConnection(
                serverName,
                commonDb,
                username,
                password,
                false
            );

            DatabaseContext.SetLicense(
                DefaultLicenseAccount,
                DefaultLicensePin
            );

            DatabaseContext.CreateConnection(
                serverName,
                databaseName,
                username,
                password,
                false
            );
        }

        private static void ValidateRequired(string name, string value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                throw new ArgumentException($"{name} is required.", name);
            }
        }
    }
}

