ALTER TABLE users
  ADD COLUMN preferred_locale ENUM('vi', 'en') NOT NULL DEFAULT 'vi';
