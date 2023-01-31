--add below trigger to survey_vital table in mlprep or equivalent database to the AFTER INSERT action

INSERT INTO `carex_uat`.`mi_vitals` -- change "carex" to the appropriate name based on the database present
(
`patient_id`,
`submitted_by`,
`bp_report`,
`bp_taken_when`,
`bp_taken_date`,
`bp_taken_time`,
`bp_posture`,
`bp_comments`,
`am_systolic_top`,
`am_diastolic_bottom`,
`pm_systolic_top`,
`pm_diastolic_bottom`,
`hr_report`,
`hr_taken_when`,
`hr_taken_date`,
`heart_rate`,
`weight_report`,
`weight_taken_when`,
`weight_taken_date`,
`weight_scale`,
`weight_pounds`,
`weight_kilograms`,
`tstamp`)
VALUES
(
NEW.patient_internal_id,
NEW.submitted_by,
NEW.bp_report,
NEW.bp_taken_when,
NEW.bp_taken_date,
NEW.bp_taken_time,
NEW.bp_posture,
NEW.bp_comments,
NEW.am_systolic_top,
NEW.am_diastolic_bottom,
NEW.pm_systolic_top,
NEW.pm_diastolic_bottom,
NEW.hr_report,
NEW.hr_taken_when,
NEW.hr_taken_date,
NEW.heart_rate,
NEW.weight_report,
NEW.weight_taken_when,
NEW.weight_taken_date,
NEW.weight_scale,
NEW.weight_pounds,
NEW.weight_kilograms,
NEW.tstamp
);