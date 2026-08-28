-- Database: thai_customs
-- Character Set: utf8mb4, Collation: utf8mb4_unicode_ci

CREATE DATABASE IF NOT EXISTS `thai_customs`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `thai_customs`;

-- ============================================================================
-- 1. DIMENSION TABLES
-- ============================================================================

-- 1.1 HS Code & Commodity Master
CREATE TABLE IF NOT EXISTS `dim_hs_code` (
    `hs_code` CHAR(8) NOT NULL COMMENT '8-digit Harmonized System Code',
    `stat_code` CHAR(3) NOT NULL DEFAULT '000' COMMENT '3-digit Statistical Code',
    `unit_code` VARCHAR(10) NOT NULL DEFAULT '' COMMENT 'Statistical Measurement Unit Code (e.g., KGM, C62, TNE)',
    `desc_th` VARCHAR(500) NULL COMMENT 'Commodity Description in Thai',
    `desc_en` VARCHAR(500) NULL COMMENT 'Commodity Description in English',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`hs_code`, `stat_code`, `unit_code`),
    INDEX `idx_hs_code` (`hs_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Dimension: HS Code & Statistical Commodity Classifications';

-- 1.2 Country Master (CIA & ISO 3166 Hierarchies)
CREATE TABLE IF NOT EXISTS `dim_country` (
    `country_code` VARCHAR(10) NOT NULL COMMENT 'ISO 2-letter Alpha-2 Country Code (e.g. US, CN, JP)',
    `alpha_3` VARCHAR(10) NULL COMMENT 'ISO 3-letter Alpha-3 Code (e.g. USA, CHN, JPN)',
    `numeric_code` INT NULL COMMENT 'Numeric Country Code (e.g. 840, 156, 392)',
    `country_name` VARCHAR(150) NOT NULL COMMENT 'Standard Country Name (ISO 3166)',
    `country_name_cia` VARCHAR(150) NULL COMMENT 'Country Name (CIA)',
    `region_cia` VARCHAR(100) NULL COMMENT 'Region Code (CIA, e.g. ASEAN, OTHER ASIA, EUROPE)',
    `iso_region` VARCHAR(100) NULL COMMENT 'ISO Region (e.g. Asia, Europe, Americas, Africa, Oceania)',
    `iso_sub_region` VARCHAR(100) NULL COMMENT 'ISO Sub Region (e.g. South-eastern Asia, Eastern Asia)',
    `iso_intermediate_region` VARCHAR(100) NULL COMMENT 'ISO Intermediate Region',
    `iso_3166_2` VARCHAR(50) NULL COMMENT 'ISO 3166-2 Reference Code',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`country_code`),
    INDEX `idx_alpha3` (`alpha_3`),
    INDEX `idx_iso_region` (`iso_region`),
    INDEX `idx_region_cia` (`region_cia`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Dimension: Comprehensive Country, CIA and ISO Regional Hierarchy';

-- 1.3 Transport Mode Master
CREATE TABLE IF NOT EXISTS `dim_transport_type` (
    `transport_code` INT NOT NULL COMMENT 'Transport Mode Code (1=Sea, 2=Air, 3=Road, etc.)',
    `transport_name_th` VARCHAR(100) NOT NULL COMMENT 'Transport Mode Name in Thai',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`transport_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Dimension: Mode of Transport';

-- 1.4 Customs Port Master
CREATE TABLE IF NOT EXISTS `dim_customs_port` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `port_name` VARCHAR(255) NOT NULL COMMENT 'Port or Loading Location Name (ด่าน/สถานที่รับบรรทุก)',
    `office_short_name` VARCHAR(50) NULL COMMENT 'Regional Office Short Name (e.g. ศภ. 3)',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_port_name_office` (`port_name`, `office_short_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Dimension: Customs Ports and Checkpoints';

-- 1.5 Customs Regional Office Master
CREATE TABLE IF NOT EXISTS `dim_customs_office` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `office_name` VARCHAR(255) NOT NULL COMMENT 'Regional Customs Office Name (สำนัก/สำนักงานศุลกากร)',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_office_name` (`office_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Dimension: Regional Customs Offices';

-- ============================================================================
-- 2. FACT TABLES (TRADE TRANSACTIONS)
-- ============================================================================

-- 2.1 Fact: Trade by Country (Import: ctm_06_11, Export: ctm_06_12)
CREATE TABLE IF NOT EXISTS `fact_trade_by_country` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `period_date` DATE NOT NULL COMMENT 'Effective Monthly Period (YYYY-MM-01)',
    `period_year` SMALLINT NOT NULL COMMENT 'Common Era Year (e.g. 2025)',
    `period_month` TINYINT NOT NULL COMMENT 'Period Month (1-12)',
    `trade_type` ENUM('IMPORT', 'EXPORT') NOT NULL COMMENT 'Trade Flow Type',
    `country_code` VARCHAR(10) NOT NULL COMMENT 'Country Code',
    `hs_code` CHAR(8) NOT NULL COMMENT '8-digit HS Code',
    `stat_code` CHAR(3) NOT NULL DEFAULT '000' COMMENT '3-digit Stat Code',
    `unit_code` VARCHAR(10) NULL COMMENT 'Statistical Unit',
    `quantity` DECIMAL(18, 4) NULL COMMENT 'Weight or Statistical Quantity',
    `value_thb` DECIMAL(18, 2) NOT NULL DEFAULT 0.00 COMMENT 'Trade Value in THB (CIF for Import, FOB for Export)',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_country_period` (`period_year`, `period_month`, `trade_type`),
    INDEX `idx_country_code` (`country_code`),
    INDEX `idx_country_hs` (`hs_code`),
    INDEX `idx_country_date` (`period_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Fact: Monthly Import and Export Trade by Country';

-- 2.2 Fact: Trade by Transport Mode (Import: ctm_06_17, Export: ctm_06_18)
CREATE TABLE IF NOT EXISTS `fact_trade_by_transport` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `period_date` DATE NOT NULL,
    `period_year` SMALLINT NOT NULL,
    `period_month` TINYINT NOT NULL,
    `trade_type` ENUM('IMPORT', 'EXPORT') NOT NULL,
    `transport_code` INT NOT NULL COMMENT 'Transport Mode Code',
    `hs_code` CHAR(8) NOT NULL,
    `stat_code` CHAR(3) NOT NULL DEFAULT '000',
    `unit_code` VARCHAR(10) NULL,
    `quantity` DECIMAL(18, 4) NULL,
    `value_thb` DECIMAL(18, 2) NOT NULL DEFAULT 0.00,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_trans_period` (`period_year`, `period_month`, `trade_type`),
    INDEX `idx_trans_code` (`transport_code`),
    INDEX `idx_trans_hs` (`hs_code`),
    INDEX `idx_trans_date` (`period_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Fact: Monthly Import and Export Trade by Transport Mode';

-- 2.3 Fact: Trade by Customs Port (Import: ctm_06_15, Export: ctm_06_16)
CREATE TABLE IF NOT EXISTS `fact_trade_by_port` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `period_date` DATE NOT NULL,
    `period_year` SMALLINT NOT NULL,
    `period_month` TINYINT NOT NULL,
    `trade_type` ENUM('IMPORT', 'EXPORT') NOT NULL,
    `port_name` VARCHAR(255) NOT NULL COMMENT 'Port / Checkpoint Name',
    `office_short_name` VARCHAR(50) NULL COMMENT 'Regional Office Short Name',
    `hs_code` CHAR(8) NOT NULL,
    `stat_code` CHAR(3) NOT NULL DEFAULT '000',
    `unit_code` VARCHAR(10) NULL,
    `quantity` DECIMAL(18, 4) NULL,
    `value_thb` DECIMAL(18, 2) NOT NULL DEFAULT 0.00,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_port_period` (`period_year`, `period_month`, `trade_type`),
    INDEX `idx_port_name` (`port_name`),
    INDEX `idx_port_hs` (`hs_code`),
    INDEX `idx_port_date` (`period_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Fact: Monthly Import and Export Trade by Customs Port';

-- 2.4 Fact: Trade by Regional Customs Office (Import: ctm_06_13, Export: ctm_06_14)
CREATE TABLE IF NOT EXISTS `fact_trade_by_office` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `period_date` DATE NOT NULL,
    `period_year` SMALLINT NOT NULL,
    `period_month` TINYINT NOT NULL,
    `trade_type` ENUM('IMPORT', 'EXPORT') NOT NULL,
    `office_name` VARCHAR(255) NOT NULL COMMENT 'Regional Customs Office Name',
    `hs_code` CHAR(8) NOT NULL,
    `stat_code` CHAR(3) NOT NULL DEFAULT '000',
    `unit_code` VARCHAR(10) NULL,
    `quantity` DECIMAL(18, 4) NULL,
    `value_thb` DECIMAL(18, 2) NOT NULL DEFAULT 0.00,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_office_period` (`period_year`, `period_month`, `trade_type`),
    INDEX `idx_office_name` (`office_name`),
    INDEX `idx_office_hs` (`hs_code`),
    INDEX `idx_office_date` (`period_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Fact: Monthly Import and Export Trade by Regional Customs Office';

-- ============================================================================
-- 3. AUDIT & INGESTION LOGGING TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS `data_ingestion_log` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `dataset_id` VARCHAR(30) NOT NULL COMMENT 'e.g. ctm_06_11',
    `period_year` SMALLINT NOT NULL COMMENT 'CE Year',
    `period_month` TINYINT NULL COMMENT 'Period Month or NULL for full year',
    `trade_type` ENUM('IMPORT', 'EXPORT') NOT NULL,
    `filename` VARCHAR(255) NOT NULL,
    `file_hash` VARCHAR(64) NULL COMMENT 'MD5 or SHA256 checksum',
    `rows_loaded` INT NOT NULL DEFAULT 0,
    `total_value_thb` DECIMAL(20, 2) NULL DEFAULT 0.00,
    `status` VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
    `message` TEXT NULL,
    `ingested_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_log_dataset` (`dataset_id`, `period_year`, `period_month`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Audit Log for Ingestion Batches and Retroactive Adjustments';
