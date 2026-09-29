-- The broker scheduler executes `retrain` jobs only (ml-broker/app/
-- scheduler_worker.py). `predict-all` has no implementation: predictions are
-- driven by the journal fan-out and ml_predict_queue, so the seeded
-- hourly-predict row would be claimed every hour and skipped forever.
--
-- Disable it explicitly instead of leaving a permanently-due row behind. The
-- row is kept (not deleted) so the intent stays visible in the table; the
-- scheduler honours `enabled`, and re-running this migration is a no-op.
UPDATE ml_schedule
   SET enabled = false
 WHERE name = 'hourly-predict'
   AND kind = 'predict-all'
   AND enabled;
