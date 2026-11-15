-- PawTrack MySQL schema (PawTrack also creates these automatically on start)
CREATE DATABASE IF NOT EXISTS `pawtrack` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `pawtrack`;

CREATE TABLE IF NOT EXISTS `animals` (
  `seq` BIGINT NOT NULL AUTO_INCREMENT,
  `animal_id` VARCHAR(64) NOT NULL,
  `qr_token` VARCHAR(191) NULL,
  `data` LONGTEXT NOT NULL,
  PRIMARY KEY (`seq`),
  UNIQUE KEY `uq_animals_animal_id` (`animal_id`),
  KEY `ix_animals_qr_token` (`qr_token`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `vaccinations` (
  `seq` BIGINT NOT NULL AUTO_INCREMENT,
  `vaccination_id` VARCHAR(64) NOT NULL,
  `animal_id` VARCHAR(191) NULL,
  `data` LONGTEXT NOT NULL,
  PRIMARY KEY (`seq`),
  UNIQUE KEY `uq_vaccinations_vaccination_id` (`vaccination_id`),
  KEY `ix_vaccinations_animal_id` (`animal_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `users` (
  `seq` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` VARCHAR(64) NOT NULL,
  `username` VARCHAR(191) NULL,
  `data` LONGTEXT NOT NULL,
  `password_hash` VARCHAR(255) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(`data`, '$.password_hash'))) STORED,
  PRIMARY KEY (`seq`),
  UNIQUE KEY `uq_users_user_id` (`user_id`),
  KEY `ix_users_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `notifications` (
  `seq` BIGINT NOT NULL AUTO_INCREMENT,
  `notification_id` VARCHAR(64) NOT NULL,
  `animal_id` VARCHAR(191) NULL,
  `data` LONGTEXT NOT NULL,
  PRIMARY KEY (`seq`),
  UNIQUE KEY `uq_notifications_notification_id` (`notification_id`),
  KEY `ix_notifications_animal_id` (`animal_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `inventory` (
  `seq` BIGINT NOT NULL AUTO_INCREMENT,
  `item_id` VARCHAR(64) NOT NULL,
  `data` LONGTEXT NOT NULL,
  PRIMARY KEY (`seq`),
  UNIQUE KEY `uq_inventory_item_id` (`item_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `inventory_transactions` (
  `seq` BIGINT NOT NULL AUTO_INCREMENT,
  `transaction_id` VARCHAR(64) NOT NULL,
  `item_id` VARCHAR(191) NULL,
  `data` LONGTEXT NOT NULL,
  PRIMARY KEY (`seq`),
  UNIQUE KEY `uq_inventory_transactions_transaction_id` (`transaction_id`),
  KEY `ix_inventory_transactions_item_id` (`item_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `pos_sales` (
  `seq` BIGINT NOT NULL AUTO_INCREMENT,
  `sale_id` VARCHAR(64) NOT NULL,
  `cashier` VARCHAR(191) NULL,
  `data` LONGTEXT NOT NULL,
  PRIMARY KEY (`seq`),
  UNIQUE KEY `uq_pos_sales_sale_id` (`sale_id`),
  KEY `ix_pos_sales_cashier` (`cashier`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `pos_services` (
  `seq` BIGINT NOT NULL AUTO_INCREMENT,
  `service_id` VARCHAR(64) NOT NULL,
  `data` LONGTEXT NOT NULL,
  PRIMARY KEY (`seq`),
  UNIQUE KEY `uq_pos_services_service_id` (`service_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `settings` (
  `setting_key` VARCHAR(100) NOT NULL,
  `setting_value` LONGTEXT NOT NULL,
  PRIMARY KEY (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `notification_reads` (
  `user_id` VARCHAR(64) NOT NULL,
  `item_key` VARCHAR(191) NOT NULL,
  `read_at` VARCHAR(40) NOT NULL,
  PRIMARY KEY (`user_id`, `item_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
