from db_ops import get_analytics_db_connect, get_db_connect


def get_id_and_username():
    """
    Returns username to internal_id map for patient, provider and caregiver
    """
    mapping = {}
    cnx = get_db_connect()
    with cnx.cursor() as cursor:
        cursor.execute("select username, internal_id from patients")
        patients = cursor.fetchall()
    mapping.update({res[0]: res[1] for res in patients if res[1] is not None})
    return mapping


def update_survey_falls_table():
    """
    Adds internal_id for patient in the falls table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_falls where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_falls set survey_falls.patient_internal_id = %%s where survey_falls.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_nausea_table():
    """
    Adds internal_id for patient in the nausea table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_nausea where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_nausea set survey_nausea.patient_internal_id = %%s where survey_nausea.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_fever_table():
    """
    Adds internal_id for patient in the fever table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_fever where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_fever set survey_fever.patient_internal_id = %%s where survey_fever.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_fatigue_table():
    """
    Adds internal_id for patient in the fatigue table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_fatigue where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_fatigue set survey_fatigue.patient_internal_id = %%s where survey_fatigue.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_breath_table():
    """
    Adds internal_id for patient in the breath table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_breath where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_breath set survey_breath.patient_internal_id = %%s where survey_breath.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_swelling_table():
    """
    Adds internal_id for patient in the swelling table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_swelling where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_swelling set survey_swelling.patient_internal_id = %%s where survey_swelling.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_weightchange_table():
    """
    Adds internal_id for patient in the weight change table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute(
                "select id from survey_weightchange where email_id=%s", (key)
            )
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_weightchange set survey_weightchange.patient_internal_id = %%s where survey_weightchange.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_chestpain_table():
    """
    Adds internal_id for patient in the chest pain table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_chestpain where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_chestpain set survey_chestpain.patient_internal_id = %%s where survey_chestpain.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_pain_table():
    """
    Adds internal_id for patient in the pain table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_pain where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_pain set survey_pain.patient_internal_id = %%s where survey_pain.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_appetite_table():
    """
    Adds internal_id for patient in the appetite table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_appetite where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_appetite set survey_appetite.patient_internal_id = %%s where survey_appetite.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_mood_table():
    """
    Adds internal_id for patient in the mood table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_mood where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_mood set survey_mood.patient_internal_id = %%s where survey_mood.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_ulcers_table():
    """
    Adds internal_id for patient in the ulcers table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_ulcers where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_ulcers set survey_ulcers.patient_internal_id = %%s where survey_ulcers.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_urinary_table():
    """
    Adds internal_id for patient in the urinary table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_urinary where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue

            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_urinary set survey_urinary.patient_internal_id = %%s where survey_urinary.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_dialysis_table():
    """
    Adds internal_id for patient in the dialysis table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_dialysis where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_dialysis set survey_dialysis.patient_internal_id = %%s where survey_dialysis.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


def update_survey_vital_table():
    """
    Adds internal_id for patient in the vital table based on patient email id
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_analytics_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from survey_vital where email_id=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if not ids:
                continue
            format_str = ",".join(["%s"] * len(ids))
            query = """ Update survey_vital set survey_vital.patient_internal_id = %%s where survey_vital.id
                    IN(%s)""" % format(
                format_str
            )
            print(mapping[key], ids)
            cursor.execute(query, ((mapping[key],) + tuple(ids)))
            cnx.commit()
    return "Updated Successfully"


if __name__ == "__main__":

    update_survey_falls_table()
    update_survey_nausea_table()
    update_survey_fever_table()
    update_survey_fatigue_table()
    update_survey_breath_table()
    update_survey_swelling_table()
    update_survey_weightchange_table()
    update_survey_chestpain_table()
    update_survey_pain_table()
    update_survey_appetite_table()
    update_survey_mood_table()
    update_survey_ulcers_table()
    update_survey_urinary_table()
    update_survey_dialysis_table()
    update_survey_vital_table()
