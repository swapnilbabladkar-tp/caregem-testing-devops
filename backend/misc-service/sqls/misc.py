INSERT_SYMPTOMS_TABLE = """ INSERT INTO mi_symptoms (patient_id, info_text, submitted_by, enter_date, 
							flag_read, survey_type, survey_id,submitter_internal_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""

INSERT_SURVEY_DIALYSIS = """ INSERT INTO survey_dialysis 
			    (submitted_by, dizzy, passedout, cramping, headaches, nausea, chestpain,
			    swelling, breath, weight, other, tstamp, patient_internal_id)
			    VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_URINARY = """INSERT INTO survey_urinary 
			   (submitted_by, report, symptons_1, symptons_2, symptons_3, pain, pain_where, kidney_stone,
			    kidney_stone_when, kidney_stone_duration, kidney_stone_passed, kidney_stone_passed_when,
			    kidney_stone_removed, kidney_stone_removed_when, tstamp, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_VITALS = """INSERT INTO survey_vital 
			   (submitted_by, bp_report, bp_taken_when, bp_taken_date, bp_taken_time, bp_posture, bp_comments,
      			am_systolic_top, am_diastolic_bottom, pm_systolic_top,
			    pm_diastolic_bottom, hr_report, hr_taken_when, hr_taken_date, heart_rate, weight_report, weight_taken_when, 
       			weight_taken_date,weight_scale, weight_pounds, weight_kilograms, tstamp, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_ULCERS = """INSERT INTO survey_ulcers 
			   (ulcers, location, size, appearance, tstamp, submitted_by, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_MOOD = """INSERT INTO survey_mood 
			   (mood, lack_interest, feeling_down, tstamp, submitted_by, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_APPETITE = """INSERT INTO survey_appetite 
			   (appetite, level, tstamp, submitted_by, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_LIGHTHEADEDNESS = """INSERT INTO survey_lightheadedness 
			   (lightheadedness, level, frequency, tstamp, submitted_by, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_PAIN = """INSERT INTO survey_pain 
			   (pain, level, location, frequency, length, tstamp, submitted_by, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_CHESTPAIN = """INSERT INTO survey_chestpain 
			   (chestpain, recentpain, restpain, level, type, length, worse, better, frequency, submitted_by, 
      			tstamp, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_WEIGHTCHANGE = """INSERT INTO survey_weightchange 
			   (submitted_by, report, period, gained_lost, lb_kg, change_in_lb, change_in_kg, tstamp, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_SWELLING = """INSERT INTO survey_swelling 
			   (swelling, level, worse, tstamp, submitted_by, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_BREATH = """INSERT INTO survey_breath 
			   (breath, level, tstamp, submitted_by, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_FATIGUE = """INSERT INTO survey_fatigue 
			   (fatigue, level, tstamp, submitted_by, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s)
			"""
INSERT_SURVEY_FEVER = """INSERT INTO survey_fever 
			   (fever, level, frequency, tstamp, submitted_by, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s)
			"""
INSERT_SURVEY_NAUSEA = """INSERT INTO survey_nausea 
			   (nausea, level, frequency, tstamp, submitted_by, patient_internal_id)
			   VALUES(%s, %s, %s, %s, %s, %s)
			"""

INSERT_SURVEY_FALLS = """ INSERT INTO 
				survey_falls (falls, level, tstamp, submitted_by, patient_internal_id) 
				values (%s, %s, %s, %s, %s)
			"""

GET_NORMALIZED_ACHES_PAIN = """ SELECT * FROM normalized_aches_pain  WHERE id = %s """

GET_NORMALIZED_APPETITE_IMPAIRMENT = (
    """ SELECT * FROM normalized_appetite_impairment  WHERE id = %s """
)

GET_NORMALIZED_CHESTPAIN = """ SELECT * FROM normalized_chest_pain  WHERE id = %s """

GET_DESC_ORDER_NORMALIZED_SHORTNESS_OF_BREATH_FOR_PATIENT = """ SELECT * from normalized_shortness_of_breath 
															WHERE internal_id = %s ORDER BY tstamp DESC"""

GET_NORMALIZED_FALLS = """ SELECT * FROM normalized_falls  WHERE id = %s """

GET_NORMALIZED_FATIGUE = """ SELECT * FROM normalized_fatigue  WHERE id = %s """

GET_NORMALIZED_FEVER = """ SELECT * FROM normalized_fever  WHERE id = %s """

GET_DESC_ORDER_NORMALIZED_ULCERS_FOR_PATIENT = (
    """ SELECT * from normalized_ulcers where internal_id = %s ORDER BY tstamp DESC"""
)

GET_NORMALIZED_LEG_SWELLING = (
    """ SELECT * FROM normalized_leg_swelling  WHERE id = %s """
)

GET_NORMALIZED_LIGHTHEADEDNESS = (
    """ SELECT * FROM normalized_lightheadedness  WHERE id = %s """
)

GET_NORMALIZED_NAUSEA = """ SELECT * FROM normalized_nausea  WHERE id = %s """


GET_NORMALIZED_SHORTNESS_OF_BREATH = (
    """ SELECT * FROM normalized_shortness_of_breath  WHERE id = %s """
)

GET_DESC_ORDER_NORMALIZED_CHESTPAIN_FOR_PATIENT = """ SELECT * from normalized_chest_pain 
													WHERE internal_id = %s ORDER BY tstamp DESC"""

GET_NORMALIZED_ULCERS = """ SELECT * FROM normalized_ulcers  WHERE id = %s """

GET_DESC_ORDER_NORMALIZED_FEVER_FOR_PATIENT = (
    """ SELECT * from normalized_fever where internal_id = %s ORDER BY tstamp DESC"""
)

GET_NETWORK_PROVIDERS = """SELECT providers.internal_id AS provider_internal_id,
       providers.external_id AS provider_external_id,
       caregivers.internal_id AS caregiver_internal_id,
       caregivers.external_id AS caregiver_external_id,
       networks.alert_receiver AS network_alert_receiver
FROM   patients
       JOIN networks
         ON networks._patient_id = patients.id
       LEFT JOIN providers
         ON providers.internal_id = networks.user_internal_id
       LEFT JOIN caregivers
         ON caregivers.internal_id = networks.user_internal_id
WHERE  patients.internal_id = %(patient_internal_id)s """

GET_ORG_NAME_FOR_PATIENT = """SELECT name AS org_name
FROM   patient_org
       JOIN organizations
         ON patient_org.organizations_id = organizations.id
       JOIN patients
         ON patients.id = patient_org.patients_id
WHERE  internal_id = %(patient_internal_id)s;
"""
