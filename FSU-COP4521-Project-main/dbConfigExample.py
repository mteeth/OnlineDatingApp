# this is just a template for YOUR dbConfig.py you can copy it all but change it for user, password, and database

import mysql.connector

def getConnection():
    return mysql.connector.connect(
        host="localhost",   
        user="username",    # enter your own username
        password="password",    # enter your own password
        database="database" # enter the name of your own database
    )
