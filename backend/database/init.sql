-- GeoSRM Engine (SIH26142) — PostGIS schema bootstrap.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$ BEGIN
    CREATE TYPE job_status AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS user_aois (
    aoi_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_label  VARCHAR(100),
    geom        GEOMETRY(Polygon, 4326) NOT NULL,
    area_sqm    DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS satellite_granules (
    granule_id             VARCHAR(100) PRIMARY KEY,
    acquisition_date       TIMESTAMP WITH TIME ZONE,
    cloud_cover_percentage DOUBLE PRECISION,
    stac_url               VARCHAR(512),
    bounding_box           GEOMETRY(Polygon, 4326)
);

CREATE TABLE IF NOT EXISTS srm_jobs (
    job_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aoi_id                 UUID REFERENCES user_aois(aoi_id) ON DELETE CASCADE,
    granule_id             VARCHAR(100) REFERENCES satellite_granules(granule_id) ON DELETE RESTRICT,
    status                 job_status NOT NULL DEFAULT 'PENDING',
    scale_factor           INT DEFAULT 4,
    miou_score             DOUBLE PRECISION,
    cog_path               VARCHAR(255),
    execution_duration_sec DOUBLE PRECISION,
    created_at             TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cog_exports (
    export_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID REFERENCES srm_jobs(job_id) ON DELETE CASCADE,
    file_path       VARCHAR(255) NOT NULL,
    crs_projection  VARCHAR(32) DEFAULT 'EPSG:4326',
    file_size_bytes BIGINT
);

CREATE TABLE IF NOT EXISTS class_metrics (
    metric_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID REFERENCES srm_jobs(job_id) ON DELETE CASCADE,
    built_up_sqm    DOUBLE PRECISION DEFAULT 0,
    road_sqm        DOUBLE PRECISION DEFAULT 0,
    water_sqm       DOUBLE PRECISION DEFAULT 0,
    vegetation_sqm  DOUBLE PRECISION DEFAULT 0,
    cropland_sqm    DOUBLE PRECISION DEFAULT 0,
    bare_soil_sqm   DOUBLE PRECISION DEFAULT 0,
    sand_sqm        DOUBLE PRECISION DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_user_aois_geom ON user_aois USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_granules_bbox ON satellite_granules USING GIST(bounding_box);
CREATE INDEX IF NOT EXISTS idx_srm_jobs_created_at ON srm_jobs(created_at DESC);
