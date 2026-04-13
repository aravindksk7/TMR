-- create_databases.sql — run once as SA against master
-- Creates Staging_DB and Reporting_DB if they do not already exist.

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'Staging_DB')
BEGIN
    CREATE DATABASE Staging_DB
        COLLATE SQL_Latin1_General_CP1_CI_AS;
    PRINT 'Created Staging_DB';
END
ELSE
    PRINT 'Staging_DB already exists';
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'Reporting_DB')
BEGIN
    CREATE DATABASE Reporting_DB
        COLLATE SQL_Latin1_General_CP1_CI_AS;
    PRINT 'Created Reporting_DB';
END
ELSE
    PRINT 'Reporting_DB already exists';
GO
