INSERT INTO athlete.activity_sources(revision_id,activity_id,provider,external_id,payload)
SELECT d.revision_id,s.activity_id,'hevy',w.item->>'hevy_workout_id',w.item
FROM athlete.datasets d
JOIN athlete.dataset_blobs b ON b.digest=d.digest
CROSS JOIN LATERAL jsonb_array_elements(b.payload) AS w(item)
LEFT JOIN athlete.strength_sessions s ON s.revision_id=d.revision_id AND s.payload->>'hevy_workout_id'=w.item->>'hevy_workout_id'
WHERE d.path='data/hevy_workouts.json'
ON CONFLICT DO NOTHING;
