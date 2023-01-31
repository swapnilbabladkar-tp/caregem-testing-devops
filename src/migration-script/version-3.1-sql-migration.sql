-- notifications

-- Run the encrypt_existing_notifications.py script before below commands

alter table notifications rename to symptom_notifications;
ALTER TABLE symptom_notifications RENAME COLUMN provider_internal_id TO notifier_internal_id;

CREATE TABLE `carex`.`message_notifications` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `message_id` TEXT NULL,
  `channel_name` VARCHAR(255) NULL,
  `notifier_internal_id` INT NULL,
  `receiver_internal_id` INT NULL,
  `sender_internal_id` INT NULL,
  `level` INT NULL,
  `notification_details` TEXT NULL,
  `created_on` DATETIME NULL,
  `created_by` INT NULL,
  `updated_on` DATETIME NULL,
  `updated_by` INT NULL,
  `notification_status` INT NULL,
  PRIMARY KEY (`id`));

CREATE TABLE `carex`.`remote_vital_notifications` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `remote_vital_id` INT NOT NULL,
  `patient_internal_id` INT NOT NULL,
  `notifier_internal_id` INT NOT NULL,
  `level` INT NOT NULL,
  `notification_details` TEXT NULL,
  `created_on` DATETIME NOT NULL,
  `created_by` INT NOT NULL,
  `updated_on` DATETIME NOT NULL,
  `updated_by` INT NOT NULL,
  `notification_status` INT NOT NULL,
  PRIMARY KEY (`id`));

CREATE TABLE `carex`.`medication_notifications` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `patient_internal_id` INT NULL,
  `medication_row_id` INT NULL,
  `notifier_internal_id` INT NULL,
  `level` INT NULL,
  `notification_details` TEXT NULL,
  `created_on` DATETIME NULL,
  `created_by` INT NULL,
  `updated_on` DATETIME NULL,
  `updated_by` INT NULL,
  `notification_status` INT NULL,
  PRIMARY KEY (`id`));
  
CREATE TABLE `carex`.`care_team_notifications` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `ct_member_internal_id` INT NOT NULL,
  `patient_internal_id` INT NOT NULL,
  `notifier_internal_id` INT NOT NULL,
  `level` INT NOT NULL,
  `notification_details` TEXT NOT NULL,
  `created_on` DATETIME NOT NULL,
  `created_by` INT NOT NULL,
  `updated_on` DATETIME NOT NULL,
  `updated_by` INT NOT NULL,
  `notification_status` INT NOT NULL,
  PRIMARY KEY (`id`));
  
--new_medication_reasons

INSERT INTO med_reasons 
    (medication_reasons, entity_active) 
VALUES 
    ('Proteinuria','Y'),
    ('Hyperkalemia (high potassium)','Y'),
    ('Hyperphosphatemia (high phosphorus)','Y'),
    ('Edema (swelling)','Y'),
    ('Shortness of Breath','Y'),
    ('Asthma','Y'),
    ('COPD','Y'),
    ('Lung','Y'),
    ('Pruritis (itching)','Y');


--Provider_degrees table
CREATE TABLE `carex`.`provider_degrees` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `provider_degree` VARCHAR(45) NULL,
  `entity_active` VARCHAR(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `provider_degree_UNIQUE` (`provider_degree` ASC) VISIBLE);

--To insert provider degrees into the 'provider_degrees' table
INSERT INTO provider_degrees 
    (provider_degree, entity_active) 
VALUES 
    ('[-]','Y'),
    ('MD','Y'),
    ('DO','Y'),
    ('RN','Y'),
    ('APN','Y'),
    ('CNS','Y'),
    ('MB.BS','Y'),
    ('(Med Assist)','Y'),
    ('CMA','Y'),
    ('RD','Y'),
    ('Pharm.D','Y'),
    ('RPh','Y'),
    ('BSW','Y'),
    ('MSW','Y'),
    ('LCSW','Y');

--Update degree from (None) to [-] in the 'providers' table.
UPDATE providers
SET degree = '[-]'
WHERE degree = '(NONE)';

