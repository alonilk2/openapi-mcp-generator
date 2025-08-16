-- MCP Runtime Orchestrator Database Initialization
-- This script creates the basic database schema for development

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create projects table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create connectors table
CREATE TABLE IF NOT EXISTS connectors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    connector_id VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    manifest JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(connector_id, version)
);

-- Create project_connectors table (many-to-many)
CREATE TABLE IF NOT EXISTS project_connectors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    connector_id UUID NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    enabled BOOLEAN DEFAULT true,
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(project_id, connector_id)
);

-- Create runtime_instances table
CREATE TABLE IF NOT EXISTS runtime_instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'stopped',
    started_at TIMESTAMP WITH TIME ZONE,
    stopped_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_projects_tenant_id ON projects(tenant_id);
CREATE INDEX IF NOT EXISTS idx_project_connectors_project_id ON project_connectors(project_id);
CREATE INDEX IF NOT EXISTS idx_runtime_instances_project_id ON runtime_instances(project_id);
CREATE INDEX IF NOT EXISTS idx_connectors_connector_id ON connectors(connector_id);

-- Insert default tenant for development
INSERT INTO tenants (id, name, slug) 
VALUES ('00000000-0000-0000-0000-000000000001', 'Default Tenant', 'default-tenant')
ON CONFLICT (slug) DO NOTHING;

-- Insert sample project
INSERT INTO projects (id, tenant_id, name, description)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    'Sample Project',
    'A sample project for testing the MCP Runtime'
)
ON CONFLICT (id) DO NOTHING;
