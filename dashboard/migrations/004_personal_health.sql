-- Personal, user-reviewed health state is separate from provider datasets.
-- Every change publishes a complete revision in the same transaction.
CREATE TABLE operations.personal_health_state (
  id text PRIMARY KEY,
  revision integer NOT NULL,
  payload text NOT NULL,
  updated_at text NOT NULL
);
CREATE TABLE operations.personal_health_revisions (
  revision integer PRIMARY KEY,
  payload text NOT NULL,
  reason text NOT NULL,
  created_at text NOT NULL
);
CREATE TABLE operations.personal_imports_state (
  id text PRIMARY KEY,
  payload text NOT NULL
);
CREATE TABLE operations.food_diary_state (
  day text PRIMARY KEY,
  payload text NOT NULL
);
CREATE TABLE operations.personal_artifacts (
  id text PRIMARY KEY,
  payload text NOT NULL
);
