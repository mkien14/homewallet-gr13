ALTER TABLE notifications
  ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN read_at DATETIME NULL,
  ADD COLUMN event_key VARCHAR(191) NULL,
  ADD KEY idx_notifications_user_created (user_id, created_at, id),
  ADD UNIQUE KEY uq_notifications_event_key (event_key);

CREATE TABLE push_subscriptions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  endpoint TEXT NOT NULL,
  endpoint_hash BINARY(32) NOT NULL,
  p256dh VARCHAR(128) NOT NULL,
  auth VARCHAR(64) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_push_subscriptions_endpoint_hash (endpoint_hash),
  KEY idx_push_subscriptions_user (user_id),
  CONSTRAINT fk_push_subscriptions_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
