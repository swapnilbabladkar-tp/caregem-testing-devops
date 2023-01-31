# Fluid metric query

FLUID_METRIC_QUERY = """
SELECT 
    index_id,
    STR_TO_DATE(run_date, '%%m/%%d/%%Y') AS run_date,
    location,
    name,
    target_weight,
    actual_ufr,
    lowest_bp_systolic,
    pre_bp_systolic,
    post_bp_systolic,
    post_wt_kg,
    avg_post_wt_kg,
    diff_postwt_calctargetwt,
    change_in_pw,
    change_in_pw_impact,
    ave_low_bp_3rx,
    avg_3day_post_sys,
    avg_3day_post_sys_bin,
    avg_3day_pre_sys,
    avg_3day_pre_sys_bin,
    idwg_percent_ehr,
    inter_dia_wt_gain,
    num_runs_bp_drop_less_50_or_avg_bp_drop_more_90,
    num_runs_bp_drop_more_equal_50_and_avg_bp_drop_less_90,
    num_runs_idwg_more_5_per,
    num_runs_lowest_bp_less_90,
    per_runs_idwg_more_5_per,
    step1_proposed_tw,
    step1_proposed_tw_reco,
    step2_proposed_tw_reco,
    ufr_to_reach_tw,
    num_runs_idwg_more_5_per,
    per_runs_idwg_more_5_per,
    per_runs_pw_tw_more_1,
    num_runs_pw_tw_more_1,
    per_runs_pw_tw_less_1_minus,
    num_runs_pw_tw_less_1_minus,
    '160' AS Threshold_Pre_BP,
    '150' AS Threshold_Post_BP,
    '90' AS Threshold_Low_BP,
    '13' AS Threshold_UFR,
    avg_ufr_run_6rx,
    avg_ufr_run_6rx_high,
    ufr_to_reach_tw,
    ufr_to_reach_tw_high,
    duration_in_hours,
    adjusted_post_wt_kg
FROM
    intervention
WHERE
    Internal_ID = %s
ORDER BY name , DATE_FORMAT(run_date, '%%m/%%d/%%Y') DESC
LIMIT 14;
"""
