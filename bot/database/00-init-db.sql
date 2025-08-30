-- 00-init-db.sql
-- This script ensures the database exists and is properly configured
-- Place this file in bot/database/ directory

-- Create the database if it doesn't exist (this runs as superuser on init)
-- Note: CREATE DATABASE cannot be executed within a transaction block,
-- so this is mainly for documentation. The database should be created 
-- by POSTGRES_DB environment variable.

-- Connect to the vsb_discord database
\c vsb_discord;

-- Create a simple version table to track schema versions
CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version INTEGER NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert initial version
INSERT INTO schema_version (version) 
SELECT 1 
WHERE NOT EXISTS (SELECT 1 FROM schema_version WHERE version = 1);

-- Grant all privileges on the database to the user
GRANT ALL PRIVILEGES ON DATABASE vsb_discord TO vsb_bot;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO vsb_bot;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO vsb_bot;