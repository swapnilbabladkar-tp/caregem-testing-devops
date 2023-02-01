from dataclasses import dataclass
import json
import logging
from datetime import datetime

import pymysql
from custom_exception import GeneralException
from shared import get_db_connect, get_headers

# Disabling "too-many-statements" refactoring error from pylint as this is legacy code
# disable pylint: disable=R0915

logger = logging.getLogger(__name__)

cnx = get_db_connect()


@dataclass
class CaGuidelineTimeData:
    dt_print_ca: str
    time_diff_ca: int
    time_print_ca: int


@dataclass
class PhosGuidelineTimeData:
    dt_print_phos: str
    time_diff_phos: int
    time_print_phos: int


def get_guidelines(patient_id):
    """
    This function
    1. Extracts Latest lab data values for selected patient
    2. Invalidates previous guidelines
    3. Creates new guidelines for entered patient_id based on latest lab data
    4. Returns latest guidelines inserted for the patient
    """
    patient_dict_rows = []

    try:
        cursor = cnx.cursor()
        new_flag = "1"
        time_now = datetime.now()

        sql = """ SELECT *
        FROM lab_data
        WHERE name = 'Creatinine'
        AND patient_id = %s
        ORDER BY date_tested DESC
        """
        cursor.execute(sql, (patient_id,))
        creat = cursor.fetchone()
        if creat:
            creat_val = creat[4]
        else:
            creat_val = -1

        sql2 = """ SELECT *
        FROM lab_data
        WHERE name = 'eGFR'
        AND patient_id = %s
        ORDER BY date_tested DESC
        """
        cursor.execute(sql2, (patient_id,))
        egfr = cursor.fetchone()
        if egfr:
            egfr_val = float(egfr[4])
        else:
            egfr_val = -1

        sql3 = """ SELECT *
        FROM lab_data
        WHERE name = 'PHOS'
        AND patient_id = %s
        ORDER BY date_tested DESC
        """
        cursor.execute(sql3, (patient_id,))
        phos = cursor.fetchone()
        if phos:
            phos_val = float(phos[4])
        else:
            phos_val = -1

        sql4 = """ SELECT *
        FROM lab_data
        WHERE name = 'CA'
        AND patient_id = %s
        ORDER BY date_tested DESC
        """
        cursor.execute(sql4, (patient_id,))
        calcium = cursor.fetchone()
        if calcium:
            calcium_val = float(calcium[4])
        else:
            calcium_val = -1

        def _show_red(str_):
            """
            Function to enclose the input string in #R and #
            if input string is not empty
            """
            if str_ == "":
                return ""
            return "#R" + str_ + "#"

        def _print_phos():
            """
            Return Phos Guideline string based on value
            """
            if phos_val < 0:
                return ""
            str_ = "Phos " + str(phos_val)

            return str_

        def _print_ca():
            """
            Return Calcium Guideline string based on value
            """
            if calcium_val < 0:
                return ""

            str_ = "Ca " + str(calcium_val)

            return str_

        def _print_cr():
            """
            Return Creatinine Guideline string based on value
            """
            if creat_val < 0:
                return ""

            str_ = "Cr " + str(creat_val)

            return str_

        def _print_egfr():
            """
            Return eGFR Guideline string based on value
            """
            if egfr_val < 0:
                return ""

            str_ = "eGFR " + str(egfr_val)

            return str_

        def set_flag_zero():
            """
            This function sets the most_recent_flag column value to 0
            on all existing guidelines for the entered patient_id.
            Thus marking the guidelines as stale
            """
            cursor = cnx.cursor()

            update_query = """UPDATE mi_guidelines SET most_recent_flag = '0' where patient_id = %s """
            cursor.execute(update_query, (patient_id,))
            cnx.commit()
            cursor.close()

            return

        def calc_ckd_stage():
            """
            This function returns the appropriate CKD stage
            based on the eGFR value entred
            """
            if egfr_val >= 90:
                ckd_stage = "CKD1"
            elif 60 <= egfr_val <= 89:
                ckd_stage = "CKD2"
            elif 45 <= egfr_val <= 59:
                ckd_stage = "CKD3A"
            elif 30 <= egfr_val <= 44:
                ckd_stage = "CKD3B"
            elif 15 <= egfr_val <= 29:
                ckd_stage = "CKD4"
            elif egfr_val < 15:
                ckd_stage = "CKD5"

            logging.info(ckd_stage)
            return ckd_stage

        def cal_mbd():
            """
            This function calculates, inserts and returns a guidleine regarding
            MBD (Mineral Bone Disease) based on the lab data entered into the function
            The function returns guideline if the calcium value > 10.2
            """
            ckd_value = calc_ckd_stage()
            guide = "No Guideline"

            if calcium_val > 10.2:
                guide = (
                    ckd_value
                    + "   "
                    + _show_red(_print_ca())
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "\n#RKDOQI MBD: Avoid Hypercalcemia#"
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)

            return guide

        def cal_monitor_pth_six():
            """
            This function calculates, inserts and returns a guidleine regarding
            PTH (Parathyroid Hormone) based on the lab data entered into the function
            The function returns guideline if
            CKD Stage is in CKD3A / CKD3B / CKD4
            and
            the time difference between last PTH test and now > 365 days
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            cursor = cnx.cursor()

            query = """ SELECT *
            FROM lab_data
            WHERE name = 'PTH'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query, (patient_id,))
            row = cursor.fetchone()

            cursor.close()
            logging.info(row)

            if row:
                pth_val = row[4]
                date_tested = row[2]
                dt_print = datetime.strftime(date_tested, "%m-%d-%Y")
                date_checked = datetime.now()
                logging.info("Tested", date_tested)
                logging.info("Checked", date_checked)

                difference = date_checked - date_tested
                time_diff = difference.total_seconds() / 3600.0

                time_print = int(time_diff / (24 * 30))
                logging.info(time_diff)
            else:
                return

            if ckd_value in ["CKD3A", "CKD3B", "CKD4"] and time_diff > 365 * 24:
                guide = (
                    ckd_value
                    + "   "
                    + "PTH "
                    + pth_val
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #Rlast test: "
                    + dt_print
                    + " ("
                    + str(time_print)
                    + " months)#"
                    + "\n#RKDOQI monitor PTH every 6-12 months#"
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        def cal_monitor_pth_three():
            """
            This function calculates, inserts and returns a guidleine regarding
            PTH (Parathyroid Hormone) based on the lab data entered into the function
            The function returns guideline if
            CKD Stage is CKD5
            and
            the time difference between last PTH test and now > 4380 hours (~6 months)
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            cursor = cnx.cursor()

            query = """ SELECT *
            FROM lab_data
            WHERE name = 'PTH'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query, (patient_id,))
            row = cursor.fetchone()

            cursor.close()
            logging.info(row)

            if row:
                pth_val = row[4]
                date_tested = row[2]
                dt_print = datetime.strftime(date_tested, "%m-%d-%Y")
                date_checked = datetime.now()
                logging.info("Tested", date_tested)
                logging.info("Checked", date_checked)

                difference = date_checked - date_tested
                time_diff = difference.total_seconds() / 3600.0
                time_print = int(time_diff / (24 * 30))
                logging.info(time_diff)
            else:
                return

            if time_diff > 4380 and ckd_value == "CKD5":
                guide = (
                    ckd_value
                    + "   "
                    + "PTH "
                    + pth_val
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #Rlast test: "
                    + dt_print
                    + " ("
                    + str(time_print)
                    + " months)#"
                    + "\n#RKDOQI monitor PTH every 3-6 months#"
                )

                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        def get_ckd_five_three_month_ca_phos_guideline(
            input_guide,
            ckd_value,
            ca_time_data: CaGuidelineTimeData,
            phos_time_data: PhosGuidelineTimeData,
        ):
            guide = input_guide
            if ca_time_data.time_diff_ca > 2190 and phos_time_data.time_diff_phos == -1:
                guide = (
                    ckd_value
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RCa: "
                    + ca_time_data.dt_print_ca
                    + " ("
                    + str(ca_time_data.time_print_ca)
                    + " months)"
                    + "   "
                    + phos_time_data.dt_print_phos
                    + "\nKDOQI monitor Ca and Phos every 1-3 months#"
                )
            elif (
                phos_time_data.time_diff_phos > 2190 and ca_time_data.time_diff_ca == -1
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RPhos: "
                    + phos_time_data.dt_print_phos
                    + " ("
                    + str(phos_time_data.time_print_phos)
                    + " months)"
                    + "   "
                    + ca_time_data.dt_print_ca
                    + "\nKDOQI monitor Ca and Phos every 1-3 months#"
                )
            elif (
                ca_time_data.time_diff_ca == -1 and phos_time_data.time_diff_phos == -1
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   "
                    + phos_time_data.dt_print_phos
                    + "   #R"
                    + ca_time_data.dt_print_ca
                    + "\nKDOQI monitor Ca and Phos every 1-3 months#"
                )
            elif (
                ca_time_data.time_diff_ca > 2190
                and phos_time_data.time_diff_phos > 2190
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RCa: "
                    + ca_time_data.dt_print_ca
                    + " ("
                    + str(ca_time_data.time_print_ca)
                    + " months)"
                    + "   Phos:"
                    + phos_time_data.dt_print_phos
                    + " ("
                    + str(phos_time_data.time_print_phos)
                    + " months)#"
                    + "\n#RKDOQI monitor Ca and Phos every 1-3 months#"
                )
            elif ca_time_data.time_diff_ca > 2190:
                guide = (
                    ckd_value
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RCa: "
                    + ca_time_data.dt_print_ca
                    + " ("
                    + str(ca_time_data.time_print_ca)
                    + " months)"
                    + "\nKDOQI monitor Ca and Phos every 1-3 months#"
                )
            elif phos_time_data.time_diff_phos > 2190:
                guide = (
                    ckd_value
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RPhos: "
                    + phos_time_data.dt_print_phos
                    + " ("
                    + str(phos_time_data.time_print_phos)
                    + " months)"
                    + "\nKDOQI monitor Ca and Phos every 1-3 months#"
                )
            elif ca_time_data.time_diff_ca == -1:
                guide = (
                    ckd_value
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #R"
                    + ca_time_data.dt_print_ca
                    + "\nKDOQI monitor Ca and Phos every 1-3 months#"
                )
            elif phos_time_data.time_diff_phos == -1:
                guide = (
                    ckd_value
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #R"
                    + phos_time_data.dt_print_phos
                    + "\nKDOQI monitor Ca and Phos every 1-3 months#"
                )
            return guide

        def cal_monitor_caphos_one():
            """
            This function calculates, inserts and returns a guidleine regarding
            moitoring of Calcuim and Phos based on the lab data entered into the function
            This function returns different guidelines based on the time difference
            observed for Calcium and Phos lab tests
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            cursor = cnx.cursor()

            query = """ SELECT *
            FROM lab_data
            WHERE name = 'CA'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query, (patient_id,))
            ca_row = cursor.fetchone()

            query2 = """ SELECT *
            FROM lab_data
            WHERE name = 'PHOS'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query2, (patient_id,))
            phos_row = cursor.fetchone()

            cursor.close()

            date_checked = datetime.now()

            if ca_row:
                date_tested_ca = ca_row[2]
                dt_print_ca = datetime.strftime(date_tested_ca, "%m-%d-%Y")
                difference_ca = date_checked - date_tested_ca
                time_diff_ca = difference_ca.total_seconds() / 3600.0
                time_print_ca = int(time_diff_ca / (24 * 30))
            else:
                time_diff_ca = -1
                dt_print_ca = "No Ca"
                time_print_ca = 0

            if phos_row:
                date_tested_phos = phos_row[2]
                dt_print_phos = datetime.strftime(date_tested_phos, "%m-%d-%Y")
                difference_phos = date_checked - date_tested_phos
                time_diff_phos = difference_phos.total_seconds() / 3600.0
                time_print_phos = int(time_diff_phos / (24 * 30))
            else:
                time_diff_phos = -1
                dt_print_phos = "No Phos"
                time_print_phos = 0

            if ckd_value == "CKD5" and (
                time_diff_ca > 2190
                or time_diff_phos > 2190
                or time_diff_ca == -1
                or time_diff_phos == -1
            ):
                ca_time_data = CaGuidelineTimeData(
                    dt_print_ca=dt_print_ca,
                    time_diff_ca=time_diff_ca,
                    time_print_ca=time_print_ca,
                )
                phos_time_data = PhosGuidelineTimeData(
                    dt_print_phos=dt_print_phos,
                    time_diff_phos=time_diff_phos,
                    time_print_phos=time_print_phos,
                )
                guide = get_ckd_five_three_month_ca_phos_guideline(
                    input_guide=guide,
                    ckd_value=ckd_value,
                    ca_time_data=ca_time_data,
                    phos_time_data=phos_time_data,
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        def get_ckd_four_six_month_ca_phos_guideline(
            input_guide,
            ckd_value,
            ca_time_data: CaGuidelineTimeData,
            phos_time_data: PhosGuidelineTimeData,
        ):
            guide = input_guide
            if ca_time_data.time_diff_ca > 4380 and phos_time_data.time_diff_phos == -1:
                guide = (
                    ckd_value
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RCa: "
                    + ca_time_data.dt_print_ca
                    + " ("
                    + str(ca_time_data.time_print_ca)
                    + " months)"
                    + "   "
                    + phos_time_data.dt_print_phos
                    + "\nKDOQI monitor Ca and Phos every 3-6 months#"
                )
            elif (
                phos_time_data.time_diff_phos > 4380 and ca_time_data.time_diff_ca == -1
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RPhos: "
                    + phos_time_data.dt_print_phos
                    + " ("
                    + str(phos_time_data.time_print_phos)
                    + " months)"
                    + "   "
                    + ca_time_data.dt_print_ca
                    + "\nKDOQI monitor Ca and Phos every 3-6 months#"
                )
            elif (
                ca_time_data.time_diff_ca == -1 and phos_time_data.time_diff_phos == -1
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #R"
                    + phos_time_data.dt_print_phos
                    + "   "
                    + ca_time_data.dt_print_ca
                    + "\nKDOQI monitor Ca and Phos every 3-6 months#"
                )
            elif (
                ca_time_data.time_diff_ca > 4380
                and phos_time_data.time_diff_phos > 4380
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RCa: "
                    + ca_time_data.dt_print_ca
                    + " ("
                    + str(ca_time_data.time_print_ca)
                    + " months)"
                    + "   Phos: "
                    + phos_time_data.dt_print_phos
                    + " ("
                    + str(phos_time_data.time_print_phos)
                    + " months)"
                    + "\nKDOQI monitor Ca and Phos every 3-6 months#"
                )
            elif ca_time_data.time_diff_ca > 4380:
                guide = (
                    ckd_value
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RCa: "
                    + ca_time_data.dt_print_ca
                    + " ("
                    + str(ca_time_data.time_print_ca)
                    + " months)"
                    + "\nKDOQI monitor Ca and Phos every 3-6 months#"
                )
            elif phos_time_data.time_diff_phos > 4380:
                guide = (
                    ckd_value
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RPhos:"
                    + phos_time_data.dt_print_phos
                    + " ("
                    + str(phos_time_data.time_print_phos)
                    + " months)"
                    + "\nKDOQI monitor Ca and Phos every 3-6 months#"
                )
            elif ca_time_data.time_diff_ca == -1:
                guide = (
                    ckd_value
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #R"
                    + ca_time_data.dt_print_ca
                    + "\nKDOQI monitor Ca and Phos every 3-6 months#"
                )
            elif phos_time_data.time_diff_phos == -1:
                guide = (
                    ckd_value
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #R"
                    + phos_time_data.dt_print_phos
                    + "\nKDOQI monitor Ca and Phos every 3-6 months#"
                )
            return guide

        def cal_monitor_caphos_three():
            """
            This function calculates, inserts and returns a guidleine regarding
            moitoring of Calcuim and Phos based on the lab data entered into the function
            This function returns different guidelines based on the time difference
            observed for Calcium and Phos lab tests
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            cursor = cnx.cursor()

            query = """ SELECT *
            FROM lab_data
            WHERE name = 'CA'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query, (patient_id,))
            ca_row = cursor.fetchone()

            query2 = """ SELECT *
            FROM lab_data
            WHERE name = 'PHOS'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query2, (patient_id,))
            phos_row = cursor.fetchone()

            cursor.close()

            date_checked = datetime.now()

            if ca_row:
                date_tested_ca = ca_row[2]
                dt_print_ca = datetime.strftime(date_tested_ca, "%m-%d-%Y")
                difference_ca = date_checked - date_tested_ca
                time_diff_ca = difference_ca.total_seconds() / 3600.0
                time_print_ca = int(time_diff_ca / (24 * 30))
            else:
                time_diff_ca = -1
                dt_print_ca = "No Ca"
                time_print_ca = 0

            if phos_row:
                date_tested_phos = phos_row[2]
                dt_print_phos = datetime.strftime(date_tested_phos, "%m-%d-%Y")
                difference_phos = date_checked - date_tested_phos
                time_diff_phos = difference_phos.total_seconds() / 3600.0
                time_print_phos = int(time_diff_phos / (24 * 30))
            else:
                time_diff_phos = -1
                dt_print_phos = "No Phos"
                time_print_phos = 0

            if ckd_value == "CKD4" and (
                time_diff_ca > 4380
                or time_diff_phos > 4380
                or time_diff_ca == -1
                or time_diff_phos == -1
            ):
                ca_time_data = CaGuidelineTimeData(
                    dt_print_ca=dt_print_ca,
                    time_diff_ca=time_diff_ca,
                    time_print_ca=time_print_ca,
                )
                phos_time_data = PhosGuidelineTimeData(
                    dt_print_phos=dt_print_phos,
                    time_diff_phos=time_diff_phos,
                    time_print_phos=time_print_phos,
                )
                guide = get_ckd_four_six_month_ca_phos_guideline(
                    input_guide=guide,
                    ckd_value=ckd_value,
                    ca_time_data=ca_time_data,
                    phos_time_data=phos_time_data,
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        def get_ckd_three_a_three_b_one_year_ca_phos_guideline(
            input_guide,
            ckd_value,
            ca_time_data: CaGuidelineTimeData,
            phos_time_data: PhosGuidelineTimeData,
        ):
            guide = input_guide
            if (
                ca_time_data.time_diff_ca > 365 * 24
                and phos_time_data.time_diff_phos == -1
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RCa: "
                    + ca_time_data.dt_print_ca
                    + " ("
                    + str(ca_time_data.time_print_ca)
                    + " months)"
                    + "   "
                    + phos_time_data.dt_print_phos
                    + "\nKDOQI monitor Ca and Phos every 6-12 months#"
                )
            elif (
                phos_time_data.time_diff_phos > 365 * 24
                and ca_time_data.time_diff_ca == -1
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RPhos: "
                    + phos_time_data.dt_print_phos
                    + " ("
                    + str(phos_time_data.time_print_phos)
                    + " months)"
                    + "   "
                    + ca_time_data.dt_print_ca
                    + "\nKDOQI monitor Ca and Phos every 6-12 months#"
                )
            elif (
                ca_time_data.time_diff_ca == -1 and phos_time_data.time_diff_phos == -1
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #R"
                    + phos_time_data.dt_print_phos
                    + "   "
                    + ca_time_data.dt_print_ca
                    + "\nKDOQI monitor Ca and Phos every 6-12 months#"
                )
            elif (
                ca_time_data.time_diff_ca > 365 * 24
                and phos_time_data.time_diff_phos > 365 * 24
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RCa: "
                    + ca_time_data.dt_print_ca
                    + " ("
                    + str(ca_time_data.time_print_ca)
                    + " months)"
                    + "   Phos test: "
                    + phos_time_data.dt_print_phos
                    + " ("
                    + str(phos_time_data.time_print_phos)
                    + " months)"
                    + "\nKDOQI monitor Ca and Phos every 6-12 months#"
                )
            elif ca_time_data.time_diff_ca > 365 * 24:
                guide = (
                    ckd_value
                    + "   "
                    + _print_ca()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RCa: "
                    + ca_time_data.dt_print_ca
                    + " ("
                    + str(ca_time_data.time_print_ca)
                    + " months)"
                    + "\nKDOQI monitor Ca and Phos every 6-12 months#"
                )
            elif phos_time_data.time_diff_phos > 365 * 24:
                guide = (
                    ckd_value
                    + "   "
                    + _print_phos()
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #RPhos:"
                    + phos_time_data.dt_print_phos
                    + " ("
                    + str(phos_time_data.time_print_phos)
                    + " months)"
                    + "\nKDOQI monitor Ca and Phos every 6-12 months#"
                )
            elif ca_time_data.time_diff_ca == -1:
                guide = (
                    ckd_value
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #R"
                    + ca_time_data.dt_print_ca
                    + "\nKDOQI monitor Ca and Phos every 6-12 months#"
                )
            elif phos_time_data.time_diff_phos == -1:
                guide = (
                    ckd_value
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #R"
                    + phos_time_data.dt_print_phos
                    + "\nKDOQI monitor Ca and Phos every 6-12 months#"
                )
            return guide

        def cal_monitor_caphos_six():
            """
            This function calculates, inserts and returns a guidleine regarding
            moitoring of Calcuim and Phos based on the lab data entered into the function
            This function returns different guidelines based on the time difference
            observed for Calcium and Phos lab tests
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            cursor = cnx.cursor()

            query = """ SELECT *
            FROM lab_data
            WHERE name = 'CA'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query, (patient_id,))
            ca_row = cursor.fetchone()

            query2 = """ SELECT *
            FROM lab_data
            WHERE name = 'PHOS'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query2, (patient_id,))
            phos_row = cursor.fetchone()

            cursor.close()

            date_checked = datetime.now()

            if ca_row:
                date_tested_ca = ca_row[2]
                dt_print_ca = datetime.strftime(date_tested_ca, "%m-%d-%Y")
                difference_ca = date_checked - date_tested_ca
                time_diff_ca = difference_ca.total_seconds() / 3600.0
                time_print_ca = int(time_diff_ca / (24 * 30))
            else:
                time_diff_ca = -1
                dt_print_ca = "No Ca"
                time_print_ca = 0

            if phos_row:
                date_tested_phos = phos_row[2]
                dt_print_phos = datetime.strftime(date_tested_phos, "%m-%d-%Y")
                difference_phos = date_checked - date_tested_phos
                time_diff_phos = difference_phos.total_seconds() / 3600.0
                time_print_phos = int(time_diff_phos / (24 * 30))
            else:
                time_diff_phos = -1
                dt_print_phos = "No Phos"
                time_print_phos = 0

            if ckd_value in ["CKD3A", "CKD3B"] and (
                time_diff_phos > 365 * 24
                or time_diff_ca > 365 * 24
                or time_diff_ca == -1
                or time_diff_phos == -1
            ):
                ca_time_data = CaGuidelineTimeData(
                    dt_print_ca=dt_print_ca,
                    time_diff_ca=time_diff_ca,
                    time_print_ca=time_print_ca,
                )
                phos_time_data = PhosGuidelineTimeData(
                    dt_print_phos=dt_print_phos,
                    time_diff_phos=time_diff_phos,
                    time_print_phos=time_print_phos,
                )
                guide = get_ckd_three_a_three_b_one_year_ca_phos_guideline(
                    input_guide=guide,
                    ckd_value=ckd_value,
                    ca_time_data=ca_time_data,
                    phos_time_data=phos_time_data,
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        def cal_reduce_phos():
            """
            This function calculates, inserts and returns a guidleine regarding
            reduction of Phos based on the lab data entered into the function
            This function returns guideline if phos value > 5
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            if phos_val > 5:
                guide = (
                    ckd_value
                    + "   eGFR "
                    + str(egfr_val)
                    + "   Creatinine "
                    + str(creat_val)
                    + "   #RPhos "
                    + str(phos_val)
                    + "#"
                    + "\n#RKDOQI Reduce Phos level to normal range#"
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        def cal_onex():
            """
            This function calculates, inserts and returns a guidleine regarding
            increasing clinic visit frequency based on the lab data and
            the time difference between now and the last visit
            The function returns guideline if one of the following is true
            along with time diff > 8760 hours (~1 year)
            1.CKD Value in CKD2 / CKD1 and uacr <= 300
            2.CKD Value is CKD3A and uacr <= 30
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            cursor = cnx.cursor()

            query = """ SELECT *
            FROM lab_data
            WHERE name = 'UACR'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query, (patient_id,))
            row = cursor.fetchone()

            cursor.close()

            if row:
                uacr = int(row[4])
                last_clinic_visit = "2018-02-15 16:05:55"
                lcv = datetime.strptime(last_clinic_visit, "%Y-%m-%d %H:%M:%S")
                lcv_print = datetime.strftime(lcv, "%m-%d-%Y")
                date_checked = datetime.now()

                difference = date_checked - lcv
                time_diff = difference.total_seconds() / 3600.0
                time_print = int(time_diff / (24 * 30))
            else:
                return

            if (
                (ckd_value in ["CKD2", "CKD1"] and uacr <= 300)
                or (ckd_value == "CKD3A" and uacr <= 30)
                and (time_diff > 8760)
            ):
                guide = (
                    ckd_value
                    + "   UACR "
                    + str(uacr)
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #Rlast visit: "
                    + lcv_print
                    + " ("
                    + str(time_print)
                    + " months)#"
                    + "\n#RKDOQI Frequency of follow up 1x per year#"
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        def cal_twox():
            """
            This function calculates, inserts and returns a guidleine regarding
            increasing clinic visit frequency based on the lab data and
            the time difference between now and the last visit
            The function returns guideline if one of the following is true
            along with time diff > 4380 hours (~6 months)
            1.CKD Value in CKD2 / CKD1 and uacr > 300
            2.CKD Value is CKD3B and uacr < 30
            3.CKD Value is CKD3A and uacr  between 30 and 300
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            cursor = cnx.cursor()

            query = """ SELECT *
            FROM lab_data
            WHERE name = 'UACR'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query, (patient_id,))
            row = cursor.fetchone()

            cursor.close()

            if row:
                uacr = int(row[4])
                last_clinic_visit = "2017-02-15 16:05:55"
                lcv = datetime.strptime(last_clinic_visit, "%Y-%m-%d %H:%M:%S")
                lcv_print = datetime.strftime(lcv, "%m-%d-%Y")
                date_checked = datetime.now()

                difference = date_checked - lcv
                time_diff = difference.total_seconds() / 3600.0
                time_print = int(time_diff / (24 * 30))
            else:
                return

            specific_ckd_stage_uacr_range_six_months = (
                (ckd_value in ["CKD2", "CKD1"] and uacr > 300)
                or (ckd_value == "CKD3B" and uacr < 30)
                or (ckd_value == "CKD3A" and 30 <= uacr <= 300)
                and (time_diff > 4380)
            )
            if specific_ckd_stage_uacr_range_six_months:
                guide = (
                    ckd_value
                    + "   UACR "
                    + str(uacr)
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #Rlast visit: "
                    + lcv_print
                    + " ("
                    + str(time_print)
                    + " months)#"
                    + "\n#RKDOQI Frequency of follow up 2x per year#"
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        def cal_threex():
            """
            This function calculates, inserts and returns a guidleine regarding
            increasing clinic visit frequency based on the lab data and
            the time difference between now and the last visit
            The function returns guideline if one of the following is true
            along with time diff > 2920 hours (~4 months)
            1.CKD Value is CKD4 and uacr <= 300
            2.CKD Value is CKD3B and uacr > 30
            3.CKD Value is CKD3A and uacr > 300
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            cursor = cnx.cursor()

            query = """ SELECT *
            FROM lab_data
            WHERE name = 'UACR'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query, (patient_id,))
            row = cursor.fetchone()

            cursor.close()

            if row:
                uacr = int(row[4])
                last_clinic_visit = "2018-02-15 16:05:55"
                lcv = datetime.strptime(last_clinic_visit, "%Y-%m-%d %H:%M:%S")
                lcv_print = datetime.strftime(lcv, "%m-%d-%Y")
                date_checked = datetime.now()

                difference = date_checked - lcv
                time_diff = difference.total_seconds() / 3600.0
                time_print = int(time_diff / (24 * 30))
            else:
                return

            specific_ckd_stage_uacr_range_four_months = (
                (ckd_value == "CKD4" and uacr <= 300)
                or (ckd_value == "CKD3B" and uacr > 30)
                or (ckd_value == "CKD3A" and uacr > 300)
                and (time_diff > 2920)
            )
            if specific_ckd_stage_uacr_range_four_months:
                guide = (
                    ckd_value
                    + "   UACR "
                    + str(uacr)
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #Rlast visit: "
                    + lcv_print
                    + " ("
                    + str(time_print)
                    + " months)#"
                    + "\n#RKDOQI Frequency of follow up 3x per year#"
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        def cal_fourx():
            """
            This function calculates, inserts and returns a guidleine regarding
            increasing clinic visit frequency based on the lab data and
            the time difference between now and the last visit
            The function returns guideline if one of the following is true
            along with time diff > 2190 hours (~3 months)
            1.CKD Value is CKD5
            2.CKD Value is CKD4 and uacr > 300
            3.CKD Value is CKD3A
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            cursor = cnx.cursor()

            query = """ SELECT *
            FROM lab_data
            WHERE name = 'UACR'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query, (patient_id,))
            row = cursor.fetchone()

            cursor.close()

            if row:
                uacr = int(row[4])
                last_clinic_visit = "2018-02-15 16:05:55"
                lcv = datetime.strptime(last_clinic_visit, "%Y-%m-%d %H:%M:%S")
                lcv_print = datetime.strftime(lcv, "%m-%d-%Y")
                date_checked = datetime.now()

                difference = date_checked - lcv
                time_diff = difference.total_seconds() / 3600.0
                time_print = int(time_diff / (24 * 30))
            else:
                return

            if (
                (ckd_value == "CKD5")
                or (ckd_value == "CKD4" and uacr > 300)
                or (ckd_value == "CKD3A")
                and (time_diff > 2190)
            ):
                guide = (
                    ckd_value
                    + "   UACR "
                    + str(uacr)
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   #Rlast visit: "
                    + lcv_print
                    + " ("
                    + str(time_print)
                    + " months)#"
                    + "\n#RKDOQI Frequency of follow up 4x per year#"
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        def cal_oral_bicarb():
            """
            This function calculates, inserts and returns a guidleine regarding
            Oral Bicarb based on the lab data and
            the time difference between now and the lab test
            The function returns guideline if
            CKD Value is in CKD1 / CKD2 / CKD3A / CKD3B / CKD4 / CKD5
            and
            CO2 value < 22
            """
            ckd_value = calc_ckd_stage()

            guide = "No Guideline"

            cursor = cnx.cursor()

            query = """ SELECT *
            FROM lab_data
            WHERE name = 'CO2'
            AND patient_id = %s
            ORDER BY date_tested DESC
            """
            cursor.execute(query, (patient_id,))
            row = cursor.fetchone()

            cursor.close()
            logging.info(row)
            if row:
                co_val = int(row[4])

            if (
                ckd_value in ["CKD1", "CKD2", "CKD3A", "CKD3B", "CKD4", "CKD5"]
                and co_val < 22
            ):
                guide = (
                    ckd_value
                    + "   "
                    + _print_egfr()
                    + "   "
                    + _print_cr()
                    + "   CO2 "
                    + str(co_val)
                    + "\n#RKDIGO CKD: GL CKD: Give oral bicarb supplementation for serum bicarb less than 22#"
                )
                cursor = cnx.cursor()

                insert_query = """INSERT INTO mi_guidelines (`patient_id`, `create_date`, `guidelines`, `most_recent_flag`) VALUES (%s, %s, %s, %s);  """
                cursor.execute(
                    insert_query,
                    (
                        patient_id,
                        time_now.strftime("%Y/%m/%d %H:%M:%S"),
                        guide,
                        new_flag,
                    ),
                )
                cnx.commit()
                cursor.close()

            logging.info(guide)
            return guide

        set_flag_zero()
        calc_ckd_stage()
        cal_mbd()
        cal_monitor_pth_six()
        cal_monitor_pth_three()
        cal_monitor_caphos_one()
        cal_monitor_caphos_three()
        cal_monitor_caphos_six()
        cal_reduce_phos()
        cal_onex()
        cal_twox()
        cal_threex()
        cal_fourx()
        cal_oral_bicarb()

        query = """SELECT * FROM mi_guidelines WHERE patient_id = %s and most_recent_flag = '1' """
        cursor.execute(query, (patient_id,))
        column_names = tuple([d[0].decode("utf8") for d in cursor.description])
        patient_dict_rows = [dict(zip(column_names, row)) for row in cursor.fetchall()]

        cursor.close()
        cnx.close()
    except pymysql.MySQLError as e:
        logging.info(e)
    except GeneralException as e:
        logging.exception(e)
    return patient_dict_rows


def lambda_handler(event, context):
    """
    The api will handle getting guidelines for a patient
    """
    patient_id = event["pathParameters"].get("patient_id")
    user_result = get_guidelines(patient_id)
    return {
        "statusCode": 200,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
