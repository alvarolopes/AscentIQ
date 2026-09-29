ALTER TABLE athlete.activity_sources ALTER COLUMN activity_id DROP NOT NULL;
CREATE INDEX activity_sources_activity ON athlete.activity_sources(revision_id,activity_id);
