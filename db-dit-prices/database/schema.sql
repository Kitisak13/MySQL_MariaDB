-- ============================================================================
-- DDL Schema for Department of Internal Trade (DIT) Product Prices
-- Target Database: MariaDB / MySQL
-- Collation: utf8mb4_unicode_ci
-- ============================================================================

CREATE DATABASE IF NOT EXISTS `dit_product_prices`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `dit_product_prices`;

-- ============================================================================
-- 1. DIMENSION TABLES
-- ============================================================================

-- 1.1 Product Master Catalog (730 Products from DIT API / Master Catalog)
CREATE TABLE IF NOT EXISTS `dim_product` (
    `product_id` VARCHAR(20) NOT NULL COMMENT 'Unique Product Code (e.g. P11001)',
    `product_name` VARCHAR(255) NOT NULL COMMENT 'Product Name in Thai',
    `category_name` VARCHAR(100) NULL COMMENT 'Category (e.g. ขายปลีก, ขายส่ง, บริการ)',
    `group_name` VARCHAR(100) NULL COMMENT 'Product Group (e.g. เนื้อสัตว์, พืชผัก, ข้าวสาร)',
    `unit` VARCHAR(50) NULL COMMENT 'Unit of Measurement (e.g. บาท/กก., บาท/ฟอง, บาท/ตัว)',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`product_id`),
    INDEX `idx_category` (`category_name`),
    INDEX `idx_group` (`group_name`),
    INDEX `idx_product_name` (`product_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Dimension: DIT Product Catalog & Units';

-- ============================================================================
-- 2. FACT TABLES
-- ============================================================================

-- 2.1 Daily Product Price Observations (~2M+ Rows)
CREATE TABLE IF NOT EXISTS `fact_daily_product_price` (
    `price_date` DATE NOT NULL COMMENT 'Observation Date (YYYY-MM-DD)',
    `product_id` VARCHAR(20) NOT NULL COMMENT 'Foreign Key to dim_product',
    `price_min` DECIMAL(10, 2) NULL COMMENT 'Minimum Price in THB',
    `price_max` DECIMAL(10, 2) NULL COMMENT 'Maximum Price in THB',
    `price_avg` DECIMAL(10, 2) NULL COMMENT 'Average Price in THB',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`price_date`, `product_id`),
    INDEX `idx_product_date` (`product_id`, `price_date`),
    INDEX `idx_date` (`price_date`),
    CONSTRAINT `fk_price_product` FOREIGN KEY (`product_id`) 
        REFERENCES `dim_product` (`product_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Fact: Daily Commodity Prices from DIT API';

-- ============================================================================
-- 3. AUDIT & PIPELINE LOGS
-- ============================================================================

CREATE TABLE IF NOT EXISTS `data_ingestion_log` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `dataset_name` VARCHAR(100) NOT NULL COMMENT 'Dataset Name (e.g. dit_price_database, monthly_api)',
    `file_or_source` VARCHAR(255) NOT NULL COMMENT 'Source file name or API endpoint description',
    `period_start` DATE NULL COMMENT 'Earliest observation date in batch',
    `period_end` DATE NULL COMMENT 'Latest observation date in batch',
    `total_rows` INT NOT NULL DEFAULT 0 COMMENT 'Number of rows inserted/updated',
    `file_hash` CHAR(64) NULL COMMENT 'SHA-256 Checksum if sourced from file',
    `status` VARCHAR(20) NOT NULL DEFAULT 'SUCCESS' COMMENT 'SUCCESS, FAILED, PARTIAL',
    `duration_seconds` DECIMAL(10, 2) NULL COMMENT 'Processing time in seconds',
    `ingested_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_dataset_source` (`dataset_name`, `file_or_source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Audit: Ingestion History and Data Provenance';
