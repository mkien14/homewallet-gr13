CREATE TABLE community_posts (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  author_id BIGINT NOT NULL,
  type ENUM('tip', 'budget_template') NOT NULL,
  title VARCHAR(120) NOT NULL,
  body VARCHAR(3000) NOT NULL,
  status ENUM('PENDING', 'APPROVED', 'HIDDEN') NOT NULL DEFAULT 'PENDING',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_community_posts_author
    FOREIGN KEY (author_id) REFERENCES users(id),
  KEY idx_community_posts_status_updated (status, updated_at, id),
  KEY idx_community_posts_author (author_id, created_at)
);
