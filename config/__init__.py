"""
MySQL / MariaDB : Django utilise `mysqlclient` s'il est installé ; sinon `PyMySQL` (100 % Python, sans compilation,
pratique sur un hébergement cPanel) est présenté à Django comme étant `MySQLdb`.
"""
try:
    import MySQLdb  # noqa: F401  (mysqlclient)
except ImportError:
    try:
        import pymysql

        pymysql.version_info = (2, 2, 1, "final", 0)  # Django exige mysqlclient >= 1.4.3
        pymysql.install_as_MySQLdb()
    except ImportError:  # PostgreSQL ou SQLite : aucun pilote MySQL nécessaire
        pass
