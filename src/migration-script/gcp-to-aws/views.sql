-- device_pairing_view
-- Validate the following view if not add it
CREATE
    ALGORITHM = UNDEFINED
    DEFINER = `dbadmin`@`%`
    SQL SECURITY DEFINER
VIEW `carex`.`device_pairing_view` AS
    SELECT
        `DP`.`id` AS `pairing_id`,
        `DR`.`imei` AS `imei`,
        `DP`.`active` AS `active`,
        `DR`.`id` AS `reading_id`,
        `DR`.`device_type` AS `device_type`,
        DATE_FORMAT(`DP`.`start_date`, '%Y-%m-%d') AS `pairing_start_date`,
        DATE_FORMAT(`DP`.`end_date`, '%Y-%m-%d') AS `pairing_end_date`,
        DATE_FORMAT(`DR`.`timestamp`, '%Y-%m-%d') AS `reading_date`,
        `DP`.`patient_internal_id` AS `patient_internal_id`
    FROM
        (`carex`.`device_pairing` `DP`
        JOIN `carex`.`device_reading` `DR`)
    WHERE
        ((`DP`.`imei` = `DR`.`imei`)
            AND (`DR`.`timestamp` > `DP`.`start_date`)
            AND ((`DR`.`timestamp` <= `DP`.`end_date`)
            OR (`DP`.`end_date` IS NULL)));



--Add the below line to all the analytics and normalized views create statements
--        `s`.`patient_internal_id` AS `internal_id`,
--but the view named analytics_lightheadness
--has this instead
--`mlprep-uat`.`analytics_lightheadedness`.`internal_id` AS `internal_id`,