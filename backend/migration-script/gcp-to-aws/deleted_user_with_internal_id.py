# Step 1:
#
#    alter table deleted_users add user_internal_id int not null;

import logging

from db_ops import get_db_connect

logger = logging.getLogger(__name__)


def get_id_and_username():
    """
    Returns username to internal_id map for patient, provider and caregiver
    """
    mapping = {}
    cnx = get_db_connect()
    with cnx.cursor() as cursor:
        cursor.execute("select username, internal_id from providers")
        providers = cursor.fetchall()
        cursor.execute("select username, internal_id from caregivers")
        caregivers = cursor.fetchall()
        cursor.execute("select username, internal_id from patients")
        patients = cursor.fetchall()
    mapping.update(
        {
            res[0]: res[1]
            for res in providers + caregivers + patients
            if res[1] is not None
        }
    )
    return mapping


def update_deleted_user_table():
    """
    Update deleted_user Table with the user internal id
    """
    mapping = get_id_and_username()
    cnx = get_db_connect()
    print(mapping)
    deleted_usernames = []
    with cnx.cursor() as cursor:
        cursor.execute("select deleted_user from deleted_users")
        deleted_usernames.extend(res[0] for res in cursor.fetchall())
    for key in deleted_usernames:
        with cnx.cursor() as cursor:
            cursor.execute("select id from deleted_users where deleted_user=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if ids and key in mapping:
                format_str = ",".join(["%s"] * len(ids))
                query = """ Update deleted_users set deleted_users.user_internal_id = %%s where deleted_users.id
                        IN(%s)""" % format(
                    format_str
                )
                # print(mapping[key], ids)
                cursor.execute(query, ((mapping[key],) + tuple(ids)))
        cnx.commit()
    return "Updated Successfully"


if __name__ == "__main__":
    update_deleted_user_table()
