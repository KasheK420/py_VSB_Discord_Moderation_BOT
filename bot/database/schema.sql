-- bot/database/schema.sql
-- PostgreSQL schema for VSB Discord Bot

-- Create database
CREATE DATABASE IF NOT EXISTS vsb_discord;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(20) PRIMARY KEY,  -- Discord user ID
    login VARCHAR(10) NOT NULL UNIQUE,  -- VSB login
    activity SMALLINT DEFAULT 0,  -- 0=inactive, 1=active
    type SMALLINT NOT NULL,  -- 0=student, 2=teacher
    verification VARCHAR(12) NOT NULL,
    real_name VARCHAR(150),
    attributes JSONB,  -- Store all OAuth2 attributes
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for users
CREATE INDEX idx_users_login ON users(login);
CREATE INDEX idx_users_activity ON users(activity);
CREATE INDEX idx_users_type ON users(type);
CREATE INDEX idx_users_verified_at ON users(verified_at);

-- Polls table
CREATE TABLE IF NOT EXISTS polls (
    id VARCHAR(48) PRIMARY KEY,  -- Message ID + Channel ID
    start TIMESTAMP NOT NULL,
    "end" TIMESTAMP NOT NULL,
    author VARCHAR(20) NOT NULL,  -- Discord user ID
    type SMALLINT DEFAULT 0,
    title VARCHAR(255) NOT NULL,
    options TEXT,
    emojis TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for polls
CREATE INDEX idx_polls_end ON polls("end");
CREATE INDEX idx_polls_author ON polls(author);

-- Migration: Import data from MySQL
-- This would need to be run separately with actual data
/*
-- Example migration from MySQL dump
INSERT INTO users (id, login, activity, type, verification, real_name, verified_at)
SELECT 
    id,
    login,
    activity,
    type,
    verification,
    scrap_real_name as real_name,
    scrap_date as verified_at
FROM mysql_users_import;
*/

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for users table
CREATE TRIGGER update_users_updated_at BEFORE UPDATE
    ON users FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();