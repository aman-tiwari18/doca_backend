/* ================================
   Grievance Management DB Schema
   ================================ */

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS tblcomplaints;
DROP TABLE IF EXISTS tblnonconvergencecompany;
DROP TABLE IF EXISTS tblconvergencecompany;
DROP TABLE IF EXISTS tblcompany;
DROP TABLE IF EXISTS tblcategory;
DROP TABLE IF EXISTS tblsector;
DROP TABLE IF EXISTS tblregistration;

SET FOREIGN_KEY_CHECKS = 1;

-- ================================
-- 1. USER REGISTRATION
-- ================================

CREATE TABLE tblregistration (

    userId INT AUTO_INCREMENT PRIMARY KEY,

    salutation VARCHAR(5),
    firstName VARCHAR(255),
    lastName VARCHAR(255),

    mobNumber BIGINT,
    password VARCHAR(200),

    stateCode VARCHAR(50),
    cityCode VARCHAR(50),
    country VARCHAR(50),

    block1 VARCHAR(50),

    adharNumber CHAR(250),

    address LONGTEXT,
    pincode INT,

    gender VARCHAR(45),
    altNumber VARCHAR(20),
    language VARCHAR(45),

    emailId VARCHAR(255) UNIQUE,

    toc INT,
    userType INT,

    status INT,

    activation VARCHAR(150),

    region VARCHAR(45),

    source VARCHAR(100),

    otpCode CHAR(6),

    regDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);

-- ================================
-- 2. SECTOR MASTER
-- ================================

CREATE TABLE tblsector (

    sectorId INT AUTO_INCREMENT PRIMARY KEY,

    sectorName VARCHAR(150) NOT NULL UNIQUE,

    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);

-- ================================
-- 3. CATEGORY MASTER
-- ================================

CREATE TABLE tblcategory (

    categoryId INT AUTO_INCREMENT PRIMARY KEY,

    sectorId INT NOT NULL,

    categoryName VARCHAR(150) NOT NULL,

    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (sectorId, categoryName),

    FOREIGN KEY (sectorId)
        REFERENCES tblsector(sectorId)
        ON DELETE CASCADE

);

-- ================================
-- 4. COMPANY MASTER
-- ================================

CREATE TABLE tblcompany (

    companyId INT AUTO_INCREMENT PRIMARY KEY,

    companyName VARCHAR(255) NOT NULL UNIQUE,

    companyType ENUM('convergence','non_convergence'),

    sectorId INT,
    categoryId INT,

    email VARCHAR(100),

    contactNumber CHAR(12),

    pincode CHAR(6),

    address TEXT,

    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (sectorId)
        REFERENCES tblsector(sectorId),

    FOREIGN KEY (categoryId)
        REFERENCES tblcategory(categoryId)

);

-- ================================
-- 5. CONVERGENCE COMPANY
-- ================================

CREATE TABLE tblconvergencecompany (

    id INT AUTO_INCREMENT PRIMARY KEY,

    companyId INT NOT NULL,

    companyShortname CHAR(100),
    companyFullname CHAR(125),
    companyHindiFullname VARCHAR(255),

    sectorId INT,

    companyEmail CHAR(170),

    postingDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    companyStatus INT NOT NULL,

    categoryId INT,

    updationDate VARCHAR(100),

    FOREIGN KEY (companyId)
        REFERENCES tblcompany(companyId),

    FOREIGN KEY (sectorId)
        REFERENCES tblsector(sectorId),

    FOREIGN KEY (categoryId)
        REFERENCES tblcategory(categoryId)

);

-- ================================
-- 6. NON-CONVERGENCE COMPANY
-- ================================

CREATE TABLE tblnonconvergencecompany (

    id INT AUTO_INCREMENT PRIMARY KEY,

    companyId INT NOT NULL,

    companyShortname CHAR(100),
    companyFullname CHAR(125),
    companyHindiFullname VARCHAR(255),

    sectorId INT,

    companyEmail CHAR(170),

    postingDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    companyStatus INT NOT NULL,

    categoryId INT,

    updationDate VARCHAR(100),

    FOREIGN KEY (companyId)
        REFERENCES tblcompany(companyId),

    FOREIGN KEY (sectorId)
        REFERENCES tblsector(sectorId),

    FOREIGN KEY (categoryId)
        REFERENCES tblcategory(categoryId)

);

-- ================================
-- 7. COMPLAINTS (MAIN TABLE)
-- ================================

CREATE TABLE tblcomplaints (

    complainNumber BIGINT AUTO_INCREMENT PRIMARY KEY,

    userId INT NOT NULL,

    userEmailId VARCHAR(70),
    userContactNumber CHAR(12),

    stateCode INT,
    purchasePlaceCode INT,

    complaintType VARCHAR(100),
    complaintMode VARCHAR(45),

    -- Replaces sectorCode, categoryCode with proper FK fields
    sectorId INT,
    categoryId INT,

    -- Separate fields for convergence and non-convergence companies
    convergenceCompanyId CHAR(5),
    convergenceCompanyName VARCHAR(120),
    nonConverganceCompanyCode INT,
    nonConverganceCompanyName TEXT,

    companyEmailId VARCHAR(70),
    companyContactNumber CHAR(12),
    companyPincode CHAR(6),

    agencyDetails TEXT,

    productValue VARCHAR(255),

    agentId BIGINT,
    agentRemark TEXT,

    fop VARCHAR(255),
    tier INT,
    referenceId VARCHAR(45),

    supportDoc1 VARCHAR(255),
    supportDoc2 VARCHAR(255),
    supportDoc3 VARCHAR(255),

    complaintDetails TEXT,

    complaintStatus CHAR(20),
    companyStatus CHAR(15),

    userComment TEXT,

    complaintRegDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    lastEditedBy INT,

    pgDocketNumber VARCHAR(100),

    userCommentDate DATETIME,

    lastUpdationDate TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    regulatorId INT,
    subCategoryName VARCHAR(255),
    deptRegulatorId CHAR(11),

    additionalStatus INT,
    nonConvergenceStatus VARCHAR(255),

    distributionId CHAR(20),
    docketType INT,
    countryCode CHAR(5),
    grievanceClassification VARCHAR(145),
    userStatus VARCHAR(45),

    -- Tracking Fields (Added)
    detailsFetched TINYINT(1) DEFAULT 0,
    detailsFetchedAt DATETIME,
    stage ENUM('new','active','aging','stale') DEFAULT 'new',

    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Relations
    FOREIGN KEY (userId)
        REFERENCES tblregistration(userId),

    FOREIGN KEY (sectorId)
        REFERENCES tblsector(sectorId),

    FOREIGN KEY (categoryId)
        REFERENCES tblcategory(categoryId)

);

-- ================================
-- 8. INDEXES (PERFORMANCE)
-- ================================

CREATE INDEX idx_complaints_stage
ON tblcomplaints(stage);

CREATE INDEX idx_complaints_fetched
ON tblcomplaints(detailsFetched);

CREATE INDEX idx_complaints_date
ON tblcomplaints(complaintRegDate);

CREATE INDEX idx_complaints_status
ON tblcomplaints(complaintStatus);

CREATE INDEX idx_complaints_user
ON tblcomplaints(userId);

CREATE INDEX idx_company_name
ON tblcompany(companyName);

CREATE INDEX idx_sector_name
ON tblsector(sectorName);

CREATE INDEX idx_category_name
ON tblcategory(categoryName);
