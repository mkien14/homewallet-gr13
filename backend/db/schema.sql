CREATE DATABASE IF NOT EXISTS homewallet
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE homewallet;

CREATE TABLE users (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  cognito_sub VARCHAR(64) NOT NULL UNIQUE,
  email VARCHAR(255) NOT NULL,
  display_name VARCHAR(100),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE households (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  owner_user_id BIGINT NOT NULL,
  invite_code VARCHAR(16) NOT NULL UNIQUE,
  currency CHAR(3) NOT NULL DEFAULT 'VND',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_user_id) REFERENCES users(id)
);

CREATE TABLE household_members (
  household_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  role ENUM('owner','member') NOT NULL,
  monthly_allowance BIGINT NULL,
  joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (household_id, user_id),
  FOREIGN KEY (household_id) REFERENCES households(id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  INDEX idx_members_user (user_id)
);

CREATE TABLE categories (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  household_id BIGINT NULL,            -- NULL = danh mục hệ thống
  name VARCHAR(100) NOT NULL,
  icon VARCHAR(50),
  is_fixed TINYINT(1) NOT NULL DEFAULT 0,
  FOREIGN KEY (household_id) REFERENCES households(id),
  UNIQUE KEY uq_cat_name (household_id, name)
);

CREATE TABLE receipts (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  household_id BIGINT NOT NULL,
  uploader_id BIGINT NOT NULL,
  s3_key VARCHAR(512) NOT NULL UNIQUE,
  content_sha256 CHAR(64) NULL,
  status ENUM('UPLOADING','UPLOADED','PROCESSING','DRAFT_READY',
              'NEEDS_REVIEW','CONFIRMED','FAILED') NOT NULL DEFAULT 'UPLOADING',
  ocr_confidence DECIMAL(5,2) NULL,
  merchant_raw VARCHAR(255) NULL,
  error_code VARCHAR(50) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  processed_at DATETIME NULL,
  FOREIGN KEY (household_id) REFERENCES households(id),
  FOREIGN KEY (uploader_id) REFERENCES users(id),
  INDEX idx_receipts_hash (household_id, content_sha256)
);

CREATE TABLE transactions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  household_id BIGINT NOT NULL,
  member_id BIGINT NOT NULL,
  receipt_id BIGINT NULL UNIQUE,
  occurred_on DATE NOT NULL,
  merchant VARCHAR(255),
  total_amount BIGINT NOT NULL,
  category_id BIGINT NULL,
  status ENUM('DRAFT','CONFIRMED') NOT NULL DEFAULT 'DRAFT',
  source ENUM('MANUAL','OCR') NOT NULL,
  note VARCHAR(500),
  idempotency_key VARCHAR(64) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (household_id) REFERENCES households(id),
  FOREIGN KEY (member_id) REFERENCES users(id),
  FOREIGN KEY (receipt_id) REFERENCES receipts(id),
  FOREIGN KEY (category_id) REFERENCES categories(id),
  UNIQUE KEY uq_tx_idem (household_id, idempotency_key),
  INDEX idx_tx_date (household_id, occurred_on),
  INDEX idx_tx_cat_date (household_id, category_id, occurred_on)
);

CREATE TABLE transaction_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  transaction_id BIGINT NOT NULL,
  description VARCHAR(255),
  quantity DECIMAL(10,3) NULL,
  unit_price BIGINT NULL,
  amount BIGINT NOT NULL,
  category_id BIGINT NULL,
  confidence DECIMAL(5,2) NULL,
  FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
  FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE budgets (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  household_id BIGINT NOT NULL,
  period CHAR(7) NOT NULL,              -- 'YYYY-MM'
  income_estimate BIGINT NOT NULL,
  savings_goal BIGINT NOT NULL DEFAULT 0,
  source ENUM('MANUAL','LLM','RULE') NOT NULL,
  status ENUM('DRAFT','ACTIVE') NOT NULL DEFAULT 'DRAFT',
  FOREIGN KEY (household_id) REFERENCES households(id),
  UNIQUE KEY uq_budget (household_id, period)
);

CREATE TABLE budget_lines (
  budget_id BIGINT NOT NULL,
  category_id BIGINT NOT NULL,
  amount BIGINT NOT NULL,
  PRIMARY KEY (budget_id, category_id),
  FOREIGN KEY (budget_id) REFERENCES budgets(id) ON DELETE CASCADE,
  FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE recurring_bills (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  household_id BIGINT NOT NULL,
  name VARCHAR(100) NOT NULL,
  category_id BIGINT NULL,
  due_day TINYINT NOT NULL,
  expected_amount BIGINT NULL,
  remind_days_before TINYINT NOT NULL DEFAULT 3,
  active TINYINT(1) NOT NULL DEFAULT 1,
  FOREIGN KEY (household_id) REFERENCES households(id),
  FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE alert_state (
  household_id BIGINT NOT NULL,
  period CHAR(7) NOT NULL,
  category_id BIGINT NOT NULL,
  threshold SMALLINT NOT NULL,          -- 80 hoặc 100
  sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (household_id, period, category_id, threshold)
);

CREATE TABLE job_runs (
  job_name VARCHAR(100) NOT NULL,
  period_key VARCHAR(50) NOT NULL,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status VARCHAR(20) NOT NULL,
  PRIMARY KEY (job_name, period_key)
);

CREATE TABLE notifications (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  type VARCHAR(50) NOT NULL,
  channel VARCHAR(20) NOT NULL,
  payload_json JSON,
  sent_at DATETIME NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE audit_logs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  actor_id BIGINT NOT NULL,
  action VARCHAR(100) NOT NULL,
  entity VARCHAR(50),
  entity_id BIGINT,
  at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Danh mục hệ thống mặc định
INSERT INTO categories (household_id, name, icon, is_fixed) VALUES
  (NULL, 'Ăn uống', 'utensils', 0),
  (NULL, 'Đi chợ, siêu thị', 'shopping-cart', 0),
  (NULL, 'Đi lại', 'bus', 0),
  (NULL, 'Điện, nước, internet', 'zap', 1),
  (NULL, 'Nhà ở', 'home', 1),
  (NULL, 'Sức khỏe', 'heart', 0),
  (NULL, 'Giáo dục', 'book', 0),
  (NULL, 'Giải trí', 'film', 0),
  (NULL, 'Khác', 'more-horizontal', 0),
  (NULL, 'Chưa phân loại', 'help-circle', 0);