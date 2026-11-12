CREATE TABLE household_membership_history (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  household_id BIGINT NOT NULL,
  household_name VARCHAR(100) NOT NULL,
  role ENUM('owner', 'member') NOT NULL,
  joined_at DATETIME NOT NULL,
  ended_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  end_reason ENUM('left', 'removed', 'dissolved') NOT NULL,
  CONSTRAINT fk_household_history_user FOREIGN KEY (user_id) REFERENCES users(id),
  KEY idx_household_history_user (user_id, ended_at, id)
);
