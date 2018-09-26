import csv


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
        # then we group by Books.id and the aggregate function group_concat(X) returns a
        # string which is the concatenation of all non-NULL values of X --> default delimiter
        # is "," but customizable with group_concat(X,Y) as Y
        # rename col group_concat(Tags.name) to tags with AS, but group_concat(Tags.name) tags
        # would also work
        c = db_con.execute(
            """SELECT Books.*, group_concat(Tags.name) AS tags
                              FROM Books
                              INNER JOIN BookTags bt ON Books.id = bt.book_id
                              INNER JOIN Tags ON Tags.tag_id = bt.tag_id
                              GROUP BY Books.id""")
        rows = c.fetchall()

        # cursor.description -> sequence of 7-item sequences each containing info describing
        # one result column
        col_names = [description[0] for description in c.description]
        csvwriter.writerow(col_names)  # header
        # write the all the rows to the file
        csvwriter.writerows(rows)
