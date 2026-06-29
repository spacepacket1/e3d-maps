-- Add consumer_exposure to NavigationSignals.
-- Tracks how many downstream consumers have acted on a signal, used by
-- detect_reflexivity to identify crowded destinations before they self-reinforce.
-- Defaults to 0 so existing rows are treated as unexposed.

ALTER TABLE NavigationSignals
    ADD COLUMN IF NOT EXISTS consumer_exposure UInt32 DEFAULT 0;
