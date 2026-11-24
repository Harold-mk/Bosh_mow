-- The app remembers whether the sidebar is reduced, from one launch to the next. The
-- browser storage of the window cannot keep it: its address changes at each launch.
ALTER TABLE settings
    ADD COLUMN sidebar_collapsed INTEGER NOT NULL DEFAULT 0
        CHECK (sidebar_collapsed IN (0, 1));
