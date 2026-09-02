-- Database: food_export
-- Character Set: utf8mb4, Collation: utf8mb4_unicode_ci

CREATE DATABASE IF NOT EXISTS `food_export`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `food_export`;

-- 1. Master Dimension: Complete 4-Level HS Code Hierarchy (2, 4, 8, 11 digits)
CREATE TABLE IF NOT EXISTS `dim_hs11_code` (
    `hs_11_code` CHAR(11) NOT NULL COMMENT '11-digit HS statistical code (e.g. 07011000000)',
    `hs_11_description_th` TEXT NULL COMMENT '11-digit commodity description in Thai',
    `hs_11_description_en` TEXT NULL COMMENT '11-digit commodity description in English',
    `hs_8_code` CHAR(8) NOT NULL COMMENT '8-digit AHTN subheading code',
    `hs_8_description_th` TEXT NULL COMMENT '8-digit subheading description in Thai',
    `hs_8_description_en` TEXT NULL COMMENT '8-digit subheading description in English',
    `hs_4_code` CHAR(4) NOT NULL COMMENT '4-digit heading code (e.g. 0701)',
    `hs_4_description_th` TEXT NULL COMMENT '4-digit heading description in Thai',
    `hs_4_description_en` TEXT NULL COMMENT '4-digit heading description in English',
    `hs_2_code` CHAR(2) NOT NULL COMMENT '2-digit chapter code (e.g. 07, 08, 10, 20)',
    `hs_2_description_th` TEXT NULL COMMENT '2-digit chapter description in Thai',
    `hs_2_description_en` TEXT NULL COMMENT '2-digit chapter description in English',
    `unit_code` VARCHAR(20) NULL COMMENT 'Unit code (e.g. KGM, C62, TNE)',
    `unit_name` VARCHAR(50) NULL COMMENT 'Unit name description',
    `first_seen_revision` SMALLINT NOT NULL COMMENT 'Earliest revision code appeared (e.g. 2007)',
    `latest_revision` SMALLINT NOT NULL COMMENT 'Latest revision code appeared (e.g. 2022)',
    `is_active_2022` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1 = Active in 2022 revision, 0 = Historical/Deprecated',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`hs_11_code`),
    INDEX `idx_hs_8` (`hs_8_code`),
    INDEX `idx_hs_4` (`hs_4_code`),
    INDEX `idx_hs_2` (`hs_2_code`),
    INDEX `idx_active` (`is_active_2022`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Master Dimension: 4-Level HS Codes across all revisions (2007-2022)';

-- 2. Dimension: Comprehensive Country & Geographical Region Catalog
CREATE TABLE IF NOT EXISTS `dim_country` (
    `country_code` VARCHAR(10) NOT NULL COMMENT 'ISO 2-letter Country Code (e.g. US, CN, JP)',
    `alpha_3` VARCHAR(10) NULL COMMENT 'ISO 3-letter Country Code',
    `numeric_code` INT NULL COMMENT 'UN M.49 Numeric Code',
    `country_name` VARCHAR(150) NOT NULL COMMENT 'Primary Country Name',
    `country_name_th` VARCHAR(150) NULL COMMENT 'Country Name in Thai',
    `country_name_en` VARCHAR(150) NULL COMMENT 'Country Name in English',
    `country_name_cia` VARCHAR(150) NULL COMMENT 'CIA World Factbook Country Name',
    `region_cia` VARCHAR(100) NULL COMMENT 'CIA Geographical Region',
    `iso_region` VARCHAR(100) NULL COMMENT 'UN ISO Region',
    `iso_sub_region` VARCHAR(100) NULL COMMENT 'UN ISO Sub-region',
    `iso_intermediate_region` VARCHAR(100) NULL COMMENT 'UN ISO Intermediate Region',
    `iso_3166_2` VARCHAR(50) NULL COMMENT 'ISO 3166-2 Code',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`country_code`),
    INDEX `idx_alpha3` (`alpha_3`),
    INDEX `idx_region_cia` (`region_cia`),
    INDEX `idx_iso_region` (`iso_region`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Dimension: Comprehensive Country & Geographical Region Catalog';

-- 3. Fact Table: Monthly Food & Commodity Export Data
CREATE TABLE IF NOT EXISTS `fact_food_export` (
    `id` BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `export_date` DATE NOT NULL COMMENT 'First day of observation month (e.g. 2016-01-01)',
    `export_year` SMALLINT NOT NULL COMMENT 'Year of export (e.g. 2015 - 2026)',
    `export_month` TINYINT NOT NULL COMMENT 'Month of export (1 - 12)',
    `country_code` VARCHAR(10) NOT NULL COMMENT 'Destination country code (FK)',
    `hs_11_code` CHAR(11) NOT NULL COMMENT '11-digit HS Code (FK)',
    `quantity` DECIMAL(18, 4) NOT NULL DEFAULT 0.0000 COMMENT 'Monthly Export Quantity',
    `acc_quantity` DECIMAL(18, 4) NOT NULL DEFAULT 0.0000 COMMENT 'Accumulated Export Quantity YTD',
    `value_usd` DECIMAL(18, 4) NOT NULL DEFAULT 0.0000 COMMENT 'Monthly Export Value (USD)',
    `acc_value_usd` DECIMAL(18, 4) NOT NULL DEFAULT 0.0000 COMMENT 'Accumulated Export Value YTD (USD)',
    `value_thb` DECIMAL(18, 4) NOT NULL DEFAULT 0.0000 COMMENT 'Monthly Export Value (THB)',
    `acc_value_thb` DECIMAL(18, 4) NOT NULL DEFAULT 0.0000 COMMENT 'Accumulated Export Value YTD (THB)',
    `unit_code` VARCHAR(20) NULL COMMENT 'Unit code',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_date_country_hs` (`export_date`, `country_code`, `hs_11_code`),
    INDEX `idx_date` (`export_date`),
    INDEX `idx_year_month` (`export_year`, `export_month`),
    INDEX `idx_hs11` (`hs_11_code`),
    INDEX `idx_country` (`country_code`),
    CONSTRAINT `fk_export_hs11` FOREIGN KEY (`hs_11_code`)
        REFERENCES `dim_hs11_code` (`hs_11_code`)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT `fk_export_country` FOREIGN KEY (`country_code`)
        REFERENCES `dim_country` (`country_code`)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Fact: Monthly Trade Report Export Statistics by Country and HS-11';

-- 4. Audit & Ingestion Logs
CREATE TABLE IF NOT EXISTS `data_ingestion_log` (
    `id` BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `dataset_name` VARCHAR(100) NOT NULL COMMENT 'Dataset identifier (e.g. dim_hs11_code_sync, monthly_export_sync)',
    `file_or_source` VARCHAR(255) NOT NULL COMMENT 'Source endpoint or batch description',
    `period_start` DATE NULL COMMENT 'Earliest observation date in batch',
    `period_end` DATE NULL COMMENT 'Latest observation date in batch',
    `total_rows` INT NOT NULL DEFAULT 0 COMMENT 'Number of rows ingested/updated',
    `file_hash` CHAR(64) NULL COMMENT 'SHA-256 Checksum if loaded from file',
    `status` VARCHAR(20) NOT NULL DEFAULT 'SUCCESS' COMMENT 'SUCCESS, PARTIAL, FAILED',
    `duration_seconds` DECIMAL(10, 2) NULL COMMENT 'Processing duration in seconds',
    `ingested_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_dataset` (`dataset_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Audit: Ingestion History and Pipeline Observability';
