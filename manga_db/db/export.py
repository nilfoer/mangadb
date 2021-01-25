import csv
import sqlite3
import datetime


def export_csv_from_sql(filename, db_con):
    """
    Fetches and writes all rows (with all cols) in db_con's database to the file filename using
    writerows() from the csv module

    writer kwargs: dialect='excel', delimiter=";"

    :param filename: Filename or path to file
    :param db_con: Connection to sqlite db
    :return: None
    """
    # newline="" <- important otherwise weird behaviour with multiline cells (adding \r) etc.
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        # excel dialect -> which line terminator(\r\n), delimiter(,) to use, when to quote
        # cells etc.
        csvwriter = csv.writer(csvfile, dialect="excel", delimiter=";")

        # get rows from db, using joins and aggregate func group_concat to combine data from
        # bridge table
        # SELECT Books.*, Tags.* and the inner joins without the group by would return
        # one row for every tag that a book has
        # the inner join joins matching (<- matching dependent on ON condition e.g. Books id
        # matching book_id in BookTags) rows from both tables --> MATCHING rows only
        # -> books without tags wouldnt be included
        # then we group by Books.id and the aggregate function group_concat(X) returns a
        # string which is the concatenation of all non-NULL values of X --> default delimiter
        # is "," but customizable with group_concat(X,Y) as Y
        c = db_con.execute("""
                -- or instead of distinct in group_concat use distinct(== eindeutig, not
                -- neccesarily DISTINCT keyword) subqueries
                -- sqlite is case-insensitive so bt.category_id is the same as bt.Category_id
                -- using this one with subqueries is even faster:
                --  LEFT JOIN from above: 47row db: ~15ms; ~2750 row db: ~1250ms
                --  SUBQUERIES from below: 47row db: ~ 5ms; ~2750 row db: ~ 160ms
                SELECT Books.*,
                    (
                        SELECT group_concat(Tag.name, ';')
                        FROM BookTag bt, Tag
                        WHERE  Books.id = bt.book_id
                        AND Tag.id = bt.tag_id
                    ) AS tags,
                    (
                        SELECT group_concat(Artist.name, ';')
                        FROM BookArtist bt, Artist
                        WHERE  Books.id = bt.book_id
                        AND Artist.id = bt.artist_id
                    ) AS artists,
                    (
                        SELECT group_concat(Category.name, ';')
                        FROM BookCategory bt, Category
                        WHERE  Books.id = bt.book_id
                        AND Category.id = bt.category_id
                    ) AS categories,
                    (
                        SELECT group_concat(Character.name, ';')
                        FROM BookCharacter bt, Character
                        WHERE  Books.id = bt.book_id
                        AND Character.id = bt.Character_id
                    ) AS characters,
                    (
                        SELECT group_concat(Collection.name, ';')
                        FROM BookCollection bt, Collection
                        WHERE  Books.id = bt.book_id
                        AND Collection.id = bt.Collection_id
                    ) AS collections,
                    (
                        SELECT group_concat(Groups.name, ';')
                        FROM BookGroups bt, Groups
                        WHERE  Books.id = bt.book_id
                        AND Groups.id = bt.Group_id
                    ) AS groups,
                    (
                        SELECT group_concat(List.name, ';')
                        FROM BookList bt, List
                        WHERE  Books.id = bt.book_id
                        AND List.id = bt.List_id
                    ) AS lists,
                    (
                        SELECT group_concat(Parody.name, ';')
                        FROM BookParody bt, Parody
                        WHERE  Books.id = bt.book_id
                        AND Parody.id = bt.Parody_id
                    ) AS parodies,
                ei.*
                FROM Books
                -- returns one row for each external info, due to outer joins also returns
                -- a row for books without external info
                -- no good way as far as i know to have it as one row (unless i know how many
                -- external infos there are per book and its the same for every book
                -- -> then i could use group_concat or subqueries with limit)
                LEFT JOIN ExternalInfo ei ON Books.id = ei.book_id
                GROUP BY Books.id, ei.id
            """)
        rows = c.fetchall()

        # cursor.description -> sequence of 7-item sequences each containing info describing
        # one result column
        col_names = [description[0] for description in c.description]
        csvwriter.writerow(col_names)  # header
        # write the all the rows to the file
        csvwriter.writerows(rows)

# also possible using FULL LEFT OUTER JOIN but subqueries is surprisingly faster
# -- inner join would only select rows that have an entry in both tables -> use left outer join
# -- distinct in group_concat to avoid duplicate values -> but cant select delimiter then
# -- which is important if values could contain commas (standard delim)
# SELECT Books.*,
#        group_concat(DISTINCT Tag.name, ';') AS tags,
#        group_concat(DISTINCT Artist.name) AS arists,
#        group_concat(DISTINCT Category.name) AS categories,
#        group_concat(DISTINCT Character.name) AS characters,
#        group_concat(DISTINCT Collection.name) AS collections,
#        group_concat(DISTINCT Groups.name) AS groups_,
#        group_concat(DISTINCT List.name) AS lists,
#        group_concat(DISTINCT Parody.name) AS parodies
# FROM Books
# LEFT JOIN BookTag bt ON Books.id = bt.book_id
# LEFT JOIN Tag ON Tag.id = bt.tag_id
# LEFT JOIN BookArtist ba ON Books.id = ba.book_id
# LEFT JOIN Artist ON Artist.id = ba.artist_id
# LEFT JOIN BookCategory bc ON Books.id = bc.book_id
# LEFT JOIN Category ON Category.id = bc.category_id
# LEFT JOIN BookCharacter bca ON Books.id = bca.book_id
# LEFT JOIN Character ON Character.id = bca.character_id
# LEFT JOIN BookCollection bco ON Books.id = bco.book_id
# LEFT JOIN Collection ON Collection.id = bco.collection_id
# LEFT JOIN BookGroups bg ON Books.id = bg.book_id
# LEFT JOIN Groups ON Groups.id = bg.group_id
# LEFT JOIN BookList bl ON Books.id = bl.book_id
# LEFT JOIN List ON List.id = bl.list_id
# LEFT JOIN BookParody bp ON Books.id = bp.book_id
# LEFT JOIN Parody ON Parody.id = bp.parody_id
# GROUP BY Books.id


def convert_or_escape_to_str(column_value):
    if column_value is None:
        return 'NULL'
    elif isinstance(column_value, datetime.date):
        # sqlite3 stores dates among others as TEXT as ISO8601 strings
        # NOTE: strftime's %Y is inconsistent between OSs; pads with 0 to 4 digits
        # on Windows but doesn't pad on linux
        # isoformat does not seemt to have that problem???
        # return f"'{column_value.strftime('%Y-%m-%d')}'"
        return f"'{column_value.isoformat()}'"
    elif isinstance(column_value, datetime.datetime):
        # return f"'{column_value.strftime('%Y-%m-%dT%H:%M:%S')}'"
        return f"'{column_value.isoformat()}'"
    elif isinstance(column_value, str):
        # escape single quotes using another one
        column_value = column_value.replace("'", "''")
        # enclose in single quotes
        return f"'{column_value}'"
    else:
        return str(column_value)


def export_to_sql(filename, db_con):
    row_fac_bu = db_con.row_factory
    db_con.row_factory = sqlite3.Row

    c = db_con.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name")
    sql_master = c.fetchall()

    # sql statement is exactly the same as when table/index/trigger was
    # created, including comments
    index_creation_statements = []
    table_names = []
    trigger_creation_statements = []
    result = ["PRAGMA foreign_keys=off;", "BEGIN TRANSACTION;"]
    for row in sql_master:
        if row['name'].startswith("sqlite_autoindex_"):
            continue
        type_name = row['type']
        if type_name == 'trigger':
            trigger_creation_statements.append((row['name'], row['sql']))
        elif type_name == 'index':
            index_creation_statements.append((row['name'], row['sql']))
        elif type_name == 'table':
            table_names.append(row['name'])
            # create all tables first
            result.append(f"{row['sql']};")
        else:
            assert 0

    # insert all the values
    for tbl_name in table_names:
        result.append(f"INSERT INTO \"{tbl_name}\" VALUES")
        table_rows = c.execute(f"SELECT * FROM {tbl_name}").fetchall()
        for i, tr in enumerate(table_rows):
            result.append(f"({','.join(convert_or_escape_to_str(c) for c in tr)})"
                          f"{';' if i == len(table_rows)-1 else ','}")

    for idx_name, idx_statement in index_creation_statements:
        result.append(f"{idx_statement};")

    for trigger_name, trigger_statement in trigger_creation_statements:
        result.append(f"{trigger_statement};")

    result.append("COMMIT;")
    result.append("PRAGMA foreign_keys=on;")

    with open(filename, 'w', encoding='UTF-8') as f:
        f.write("\n".join(result))

    db_con.row_factory = row_fac_bu
