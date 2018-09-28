def add_language(db_con, language):
    c = db_con.execute("INSERT OR IGNORE INTO Languages (name) VALUES (?)", (language,))
    return c.lastrowid
