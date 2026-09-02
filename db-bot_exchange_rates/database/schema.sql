-- Database: bot_exchange_rates
-- Character Set: utf8mb4, Collation: utf8mb4_unicode_ci

CREATE DATABASE IF NOT EXISTS `bot_exchange_rates`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `bot_exchange_rates`;

-- 1. Dimension Table: Currency Master
CREATE TABLE IF NOT EXISTS `dim_currency` (
    `currency_code` CHAR(3) NOT NULL COMMENT 'ISO 4217 3-letter currency code (e.g., USD, JPY, EUR)',
    `country_name` VARCHAR(100) NOT NULL COMMENT 'Country or economic zone name in Thai',
    `currency_name` VARCHAR(100) NOT NULL COMMENT 'Currency unit name in Thai',
    `unit_multiplier` INT NOT NULL DEFAULT 1 COMMENT 'Calculation unit multiplier (e.g., JPY=100, IDR=1000, others=1)',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`currency_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Master Dimension Table for Currencies';

-- 2. Fact Table: Daily Exchange Rates
CREATE TABLE IF NOT EXISTS `fact_daily_exchange_rate` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Surrogate Primary Key',
    `rate_date` DATE NOT NULL COMMENT 'Exchange rate effective date (YYYY-MM-DD)',
    `currency_code` CHAR(3) NOT NULL COMMENT 'Foreign Key referencing dim_currency',
    `buying_sight_bill` DECIMAL(12, 4) NULL COMMENT 'Buying rate for sight bills (อัตราซื้อตั๋วเงิน)',
    `buying_transfer` DECIMAL(12, 4) NULL COMMENT 'Buying rate for telegraphic transfers (อัตราซื้อเงินโอน/ซื้อ)',
    `selling` DECIMAL(12, 4) NULL COMMENT 'Selling rate (อัตราขาย)',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_rate_date_currency` (`rate_date`, `currency_code`),
    INDEX `idx_rate_date` (`rate_date`),
    INDEX `idx_currency_code` (`currency_code`),
    CONSTRAINT `fk_fact_currency` FOREIGN KEY (`currency_code`) 
        REFERENCES `dim_currency` (`currency_code`) 
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Fact Table for Bank of Thailand Daily Exchange Rates';

-- 3. Audit & Ingestion Logs
CREATE TABLE IF NOT EXISTS `data_ingestion_log` (
    `id` BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `dataset_name` VARCHAR(100) NOT NULL COMMENT 'Dataset Name (e.g. historical_backfill, monthly_batch)',
    `file_or_source` VARCHAR(255) NOT NULL COMMENT 'Source file name or batch description',
    `period_start` DATE NULL COMMENT 'Earliest observation date in batch',
    `period_end` DATE NULL COMMENT 'Latest observation date in batch',
    `total_rows` INT NOT NULL DEFAULT 0 COMMENT 'Number of rows inserted/updated',
    `file_hash` CHAR(64) NULL COMMENT 'SHA-256 Checksum of source file',
    `status` VARCHAR(20) NOT NULL DEFAULT 'SUCCESS' COMMENT 'SUCCESS, FAILED',
    `duration_seconds` DECIMAL(10, 2) NULL COMMENT 'Processing time in seconds',
    `ingested_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_dataset_source` (`dataset_name`, `file_or_source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Audit: Ingestion History and Data Provenance';
