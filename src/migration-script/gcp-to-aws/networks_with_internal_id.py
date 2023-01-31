# Step 1:
#    alter table networks add user_internal_id int not null;

from db_ops import get_db_connect


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
    mapping.update(
        {res[0]: res[1] for res in providers + caregivers if res[1] is not None}
    )
    return mapping


def update_network_table():
    """
    Adds internal_id of the provider/ caregivers to each row of
    network table based on username of provider
    """
    mapping = get_id_and_username()
    print(mapping)
    cnx = get_db_connect()
    # print(network_usernames)
    for key in mapping:
        with cnx.cursor() as cursor:
            cursor.execute("select id from networks where connected_user=%s", (key))
            ids = [res[0] for res in cursor.fetchall()]
            if ids:
                format_str = ",".join(["%s"] * len(ids))
                query = """ Update networks set networks.user_internal_id = %%s where networks.id
                        IN(%s)""" % format(
                    format_str
                )
                # print(mapping[key], ids)
                cursor.execute(query, ((mapping[key],) + tuple(ids)))
        cnx.commit()
    return "Updated Successfully"


if __name__ == "__main__":
    update_network_table()
