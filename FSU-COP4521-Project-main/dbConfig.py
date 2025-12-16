import mysql.connector 

def getConnection():
    return mysql.connector.connect(
            host ="localhost",
            user ="dating_user",
            password = "COP4521",
            database = "dating_app"
        )