SET SQL_SAFE_UPDATES = 0;

use carex_uat;

-- deleted_user
alter table deleted_users add user_internal_id int not null;

-- networks
alter table networks add user_internal_id int not null;

-- patients
alter table patients add hash_fname char(64) not null;
alter table patients add hash_lname char(64) not null;
alter table patients add hash_dob char(64) not null;
alter table patients add hash_ssn char(64) not null;

-- chime_chats
CREATE TABLE `chime_chats` (
  `id` int NOT NULL AUTO_INCREMENT,
  `channel_name` varchar(255) NOT NULL,
  `channel_arn` varchar(255) NOT NULL,
  `chime_bearer_arn` varchar(255) NOT NULL,
  `user_info` json NOT NULL,
  `channel_role` varchar(255) not null,
  `is_deleted` TINYINT DEFAULT(0),
  `is_patient_enabled` TINYINT DEFAULT(0),
  `created_on` datetime NOT NULL DEFAULT (UTC_TIMESTAMP()),
  `created_by` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE (channel_name),
  UNIQUE (channel_arn)
);

-- Run this if not set

ALTER table chime_chats add column latest_message text, add column latest_message_timestamp datetime, add column latest_message_sender varchar(50);

-- notifications

SET SQL_SAFE_UPDATES = 0;
alter table mi_symptoms add submitter_internal_id int;
alter table notifications modify medical_data_type varchar(255);
update notifications set medical_data_type = 'symptoms' where medical_data_type = 0;
alter table notifications add notification_details text;
alter table notifications add created_on datetime;
alter table notifications add created_by int;
alter table notifications add updated_on datetime;
alter table notifications add updated_by int;
alter table notifications add notification_status int;
update notifications set notification_status = 0;

-- call logs
ALTER TABLE call_logs
    ADD COLUMN meeting_id varchar(50),
    ADD COLUMN end_timestamp datetime,
    ADD COLUMN title varchar(100),
    ADD COLUMN participant_info json,
    ADD COLUMN status varchar(50),
    ADD COLUMN scheduled_time datetime;

ALTER TABLE call_logs MODIFY start_timestamp datetime;
ALTER TABLE call_logs MODIFY duration int;
update call_logs set status = 'COMPLETED' WHERE meeting_id is NULL;

-- user_exceptions

CREATE TABLE `user_exceptions` (
    `id` INT NOT NULL AUTO_INCREMENT,
    matching_external_id VARCHAR(50) NOT NULL,
    ref_uid VARCHAR(50) NULL,
    cds_or_s3_file_path VARCHAR(100) NULL,
    matching_fields VARCHAR(255) NOT NULL,
    org_id INT,
    matching_org_id INT,
    status VARCHAR(50),
    comments TEXT NULL,
    created_by INT,
    created_on DATETIME NOT NULL,
    updated_by INT,
    updated_on DATETIME,
    PRIMARY KEY (`id`)
);

-- med_discontinue

CREATE TABLE med_discontinue (
    id INT PRIMARY KEY auto_increment,
    discontinue_code INT NOT NULL,
    discontinue_reason VARCHAR(255),
    entity_active VARCHAR(1),
    UNIQUE (discontinue_reason)
);

INSERT INTO med_discontinue
            (discontinue_reason,
             discontinue_code,
             entity_active)
VALUES     ('Dose Adjustment', 1, 'Y'),
            ('Alternative Treatment', 2, 'Y'),
            ('Completion Of Treatment', 3, 'Y'),
            ('Drug interaction', 4, 'Y'),
            ('Drug Disease incompatibility', 5, 'Y'),
            ('Ineffective Medication', 6, 'Y'),
            ('Incorrect Entry', 7, 'Y'),
            ('Allergic Reaction', 8, 'Y'),
            ('Other Adverse Reaction', 9, 'Y'),
            ('Other', 999, 'Y');

-- medication
Alter table medication Add discontinue_reasons text null;

alter table medication modify unit_code varchar(25);
alter table medication modify unit_strength varchar(25);

delete from med_duration where id = 7 -- Delete the extra "hours" present at id = 7

--change_log
alter table change_log add column version int not null;

-- mi_vitals

UPDATE mi_vitals SET bp_taken_date = str_to_date(bp_taken_date, '%m/%d/%Y %H:%i:%s');
ALTER TABLE mi_vitals MODIFY bp_taken_date DATETIME;
UPDATE mi_vitals SET bp_taken_date = NULL WHERE bp_taken_date = '0000-00-00 00:00:00';

UPDATE mi_vitals SET hr_taken_date = str_to_date(hr_taken_date, '%m/%d/%Y %H:%i:%s');
ALTER TABLE mi_vitals MODIFY hr_taken_date DATETIME;
UPDATE mi_vitals SET hr_taken_date = NULL WHERE hr_taken_date = '0000-00-00 00:00:00';

UPDATE mi_vitals SET weight_taken_date = str_to_date(weight_taken_date, '%m/%d/%Y %H:%i:%s');
ALTER TABLE mi_vitals MODIFY weight_taken_date DATETIME;
UPDATE mi_vitals SET weight_taken_date = NULL WHERE weight_taken_date = '0000-00-00 00:00:00';

ALTER TABLE mi_vitals MODIFY tstamp DATETIME;

-- locked_user

alter table locked_user add external_id varchar(50) not null;
alter table locked_user add attempts int not null;

-- organizations
alter table organizations add phone_1_country_code varchar(10);
alter table organizations add phone_2_country_code varchar(10);
update organizations set phone_1_country_code="+1",phone_2_country_code="+1";


USE `mlprep-uat`;

-- survey_falls
UPDATE survey_falls SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_falls MODIFY tstamp DATETIME;
alter table survey_falls add patient_internal_id int not null;

-- survey_nausea
UPDATE survey_nausea SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_nausea MODIFY tstamp DATETIME;
alter table survey_nausea add patient_internal_id int not null;

 -- survey_fever
UPDATE survey_fever SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_fever MODIFY tstamp DATETIME;
alter table survey_fever add patient_internal_id int not null;

-- survey_fatigue
UPDATE survey_fatigue SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_fatigue MODIFY tstamp DATETIME;
alter table survey_fatigue add patient_internal_id int not null;

-- survey_breath
UPDATE survey_breath SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_breath MODIFY tstamp DATETIME;
alter table survey_breath add patient_internal_id int not null;

-- survey_swelling
UPDATE survey_swelling SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_swelling MODIFY tstamp DATETIME;
alter table survey_swelling add patient_internal_id int not null;

-- survey_weightchange
UPDATE survey_weightchange SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_weightchange MODIFY tstamp DATETIME;
alter table survey_weightchange add patient_internal_id int not null;

-- survey_chestpain
UPDATE survey_chestpain SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_chestpain MODIFY tstamp DATETIME;
alter table survey_chestpain add patient_internal_id int not null;

-- survey_pain
UPDATE survey_pain SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_chestpain MODIFY tstamp DATETIME;
alter table survey_pain add patient_internal_id int not null;

-- survey_lightheadedness

UPDATE survey_lightheadedness SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_lightheadedness MODIFY tstamp DATETIME;
alter table survey_lightheadedness add patient_internal_id int not null;

-- survey_appetite

UPDATE survey_appetite SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_appetite MODIFY tstamp DATETIME;
alter table survey_appetite add patient_internal_id int not null;

-- survey_mood

UPDATE survey_mood SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_mood MODIFY tstamp DATETIME;
alter table survey_mood add patient_internal_id int not null;

-- survey_ulcers

UPDATE survey_ulcers SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_ulcers MODIFY tstamp DATETIME;
alter table survey_ulcers add patient_internal_id int not null;

-- survey_urinary

UPDATE survey_urinary SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_urinary MODIFY tstamp DATETIME;
alter table survey_urinary add patient_internal_id int not null;

-- survey_dialysis
UPDATE survey_dialysis SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_dialysis MODIFY tstamp DATETIME;
alter table survey_dialysis add patient_internal_id int not null;

-- survey_vital

UPDATE survey_vital SET tstamp = str_to_date(tstamp, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_vital MODIFY tstamp DATETIME;
alter table survey_vital add patient_internal_id int not null;

UPDATE survey_vital SET bp_taken_date = str_to_date(bp_taken_date, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_vital MODIFY bp_taken_date DATETIME;
UPDATE survey_vital SET bp_taken_date = NULL WHERE bp_taken_date = '0000-00-00 00:00:00';

UPDATE survey_vital SET hr_taken_date = str_to_date(hr_taken_date, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_vital MODIFY hr_taken_date DATETIME;
UPDATE survey_vital SET hr_taken_date = NULL WHERE hr_taken_date = '0000-00-00 00:00:00';

UPDATE survey_vital SET weight_taken_date = str_to_date(weight_taken_date, '%m/%d/%Y %H:%i:%s');
ALTER TABLE survey_vital MODIFY weight_taken_date DATETIME;
UPDATE survey_vital SET weight_taken_date = NULL WHERE weight_taken_date = '0000-00-00 00:00:00';
