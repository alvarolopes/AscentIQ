ALTER TABLE operations.personal_health_state     ALTER COLUMN payload TYPE jsonb USING payload::jsonb;
ALTER TABLE operations.personal_health_revisions ALTER COLUMN payload TYPE jsonb USING payload::jsonb;
ALTER TABLE operations.personal_imports_state    ALTER COLUMN payload TYPE jsonb USING payload::jsonb;
ALTER TABLE operations.food_diary_state          ALTER COLUMN payload TYPE jsonb USING payload::jsonb;
ALTER TABLE operations.personal_artifacts        ALTER COLUMN payload TYPE jsonb USING payload::jsonb;
ALTER TABLE operations.jobs                      ALTER COLUMN warnings TYPE jsonb USING COALESCE(NULLIF(warnings,''),'[]')::jsonb;
CREATE INDEX IF NOT EXISTS personal_artifacts_kind ON operations.personal_artifacts ((split_part(id, ':', 1)));
