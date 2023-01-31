import logging
import os
import sys

import pymysql

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s:%(message)s"
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv

load_dotenv()


def get_db_connect():
    """
    Returns PyMysql Connection object.
    :param None
    :return: db connection.
    """
    connection = None
    db_details = {
        "host": "localhost",
        "username": "root",
        "password": "password",
        "dbname": "carex",
    }
    try:
        if not connection:
            connection = pymysql.connect(
                host=db_details["host"],
                user=db_details["username"],
                passwd=db_details["password"],
                db=db_details["dbname"],
                connect_timeout=5,
            )
    except pymysql.MySQLError as err:
        logger.error(err)
        sys.exit()
    else:
        return connection


def get_analytics_db_connect():
    """
    Returns PyMysql Connection object.
    :param None
    :return: db connection.
    """
    connection = None
    # The following used as for local connection will be commented
    db_details = {
        "host": os.getenv("DB_HOST"),
        "username": os.getenv("UNAME"),
        "password": os.getenv("PASSWORD"),
        "dbname": os.getenv("DB_MLPREP"),
    }
    try:
        if not connection:
            connection = pymysql.connect(
                host=db_details["host"],
                user=db_details["username"],
                passwd=db_details["password"],
                db=db_details["dbname"],
                connect_timeout=5,
            )
    except pymysql.MySQLError as err:
        logger.error(err)
        sys.exit()
    else:
        return connection
