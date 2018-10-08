import logging

from .util import joined_col_name_to_query_names, prod

logger = logging.getLogger(__name__)


def search_assoc_col_intersection(db_con,
                                  col,
                                  values,
                                  order_by="Books.id DESC"):
    """Searches for entries containing all values in col and returns the rows as
    a list of sqlite3.Row objects
    :param db_con: Open connection to database
    :param tags: List of tags as strings
    :return List of sqlite3.Row objects"""
    # could add default param and change having count len(values) to 1 if i want a union/or
    # instead of intersection/and
    table_name, bridge_col_name = joined_col_name_to_query_names(col)

    # dynamically insert correct nr (as many ? as elements in tags) of ? in SQLite
    # query using join on ", " and ["?"] * amount
    # then unpack list with arguments using *tags

    # for tag: SQLite Query -> select alls columns in Books
    # tagids must match AND name of the tag(singular) must be in tags list
    # bookids must match
    # results are GROUPed BY Books.id and only entries are returned that occur
    # ? (=nr of tags in tags) times --> matching all tags

    c = db_con.execute(f"""
                  SELECT Books.*
                  FROM Book{table_name} bx, Books, {table_name}
                  WHERE bx.{bridge_col_name} = {table_name}.id
                  AND ({table_name}.name IN ({', '.join(['?']*len(values))}))
                  AND Books.id = bx.book_id
                  GROUP BY Books.id
                  HAVING COUNT( Books.id ) = ?
                  ORDER BY {order_by}""", (*values, len(values)))

    return c.fetchall()


def search_mult_assoc_col_intersect(db_con, col_values_dict, order_by="Books.id DESC"):
    # nr of items in values multiplied is nr of rows returned needed to match
    # all conditions
    mul_values = prod((len(vals) for vals in col_values_dict.values()))

    # containing table names for FROM .. stmt
    table_bridge_names = []
    # conditionals
    cond_statements = []
    # vals in order the stmts where inserted for sql param sub
    vals_in_order = []
    # build conditionals for select string
    for col, vals in col_values_dict.items():
        table_name, bridge_col_name = joined_col_name_to_query_names(col)
        table_bridge_names.append(table_name)
        table_bridge_names.append(f"Book{table_name}")

        cond_statements.append(f"{'AND' if cond_statements else 'WHERE'} "
                               f"Books.id = Book{table_name}.book_id")
        cond_statements.append(f"AND {table_name}.id = Book{table_name}.{bridge_col_name}")
        cond_statements.append(f"AND {table_name}.name IN ({','.join(['?']*len(vals))})")
        vals_in_order.extend(vals)

    table_bridge_names = ", ".join(table_bridge_names)
    cond_statements = "\n".join(cond_statements)

    c = db_con.execute(f"""
            SELECT Books.*
            FROM Books, {table_bridge_names}
            {cond_statements}
            GROUP BY Books.id HAVING COUNT(Books.id) = {mul_values}
            ORDER BY {order_by}""", (*vals_in_order,))
    return c.fetchall()


def search_assoc_col_exclude(db_con,
                             col,
                             values,
                             order_by="Books.id DESC"):
    table_name, bridge_col_name = joined_col_name_to_query_names(col)
    # select all Books.ids that contain these tags (OR, would be AND with HAVING COUNT)
    # -> select all rows whose ids are not in the sub-query
    # == values are ORed, AND would be GROUP BY Books.id
    # AND HAVING COUNT ( Books.id ) = len(values) in subquery
    c = db_con.execute(f"""
                  SELECT Books.*
                  FROM Books
                  WHERE Books.id NOT IN (
                          SELECT Books.id
                          FROM Book{table_name} bx, Books, {table_name}
                          WHERE Books.id = bx.book_id
                          AND bx.{bridge_col_name} = {table_name}.id
                          AND {table_name}.name IN ({', '.join(['?']*len(values))})
                )
                ORDER BY {order_by}""", (*values, ))
    # ^^ use *values, -> , to ensure its a tuple when only one val supplied

    return c.fetchall()


def search_mult_assoc_col_exclude(db_con,
                                  col_values_dict,
                                  order_by="Books.id DESC"):
    cond_statements = []
    # vals in order the stmts where inserted for sql param sub
    vals_in_order = []
    # build conditionals for select string
    for col, vals in col_values_dict.items():
        table_name, bridge_col_name = joined_col_name_to_query_names(col)
        cond_statements.append(f"""
                 {'AND' if cond_statements else 'WHERE'} Books.id NOT IN (
                          SELECT Books.id
                          FROM Book{table_name} bx, Books, {table_name}
                          WHERE Books.id = bx.book_id
                          AND bx.{bridge_col_name} = {table_name}.id
                          AND {table_name}.name IN ({', '.join(['?']*len(vals))})
                )""")
        vals_in_order.extend(vals)
    cond_statements = "\n".join(cond_statements)

    c = db_con.execute(f"""
                  SELECT Books.*
                  FROM Books
                  {cond_statements}
                  ORDER BY {order_by}""", (*vals_in_order, ))
    # ^^ use *values, -> , to ensure its a tuple when only one val supplied

    return c.fetchall()


def search_assoc_col_intersection_exclude(db_con,
                                          col,
                                          values_and,
                                          values_ex,
                                          order_by="Books.id DESC"):
    table_name, bridge_col_name = joined_col_name_to_query_names(col)
    and_cond = f"AND ({table_name}.name IN ({', '.join(['?']*len(values_and))}))"
    and_count = f"HAVING COUNT( Books.id ) = {len(values_and)}"
    ex_cond = f"""
                  AND Books.id NOT IN (
                    SELECT Books.id
                    FROM Book{table_name} bx, Books, {table_name}
                    WHERE Books.id = bx.book_id
                    AND bx.tag_id = {table_name}.id
                    AND {table_name}.name IN ({', '.join(['?']*len(values_ex))})
                  )"""

    c = db_con.execute(f"""
                  SELECT Books.*
                  FROM Book{table_name} bx, Books, {table_name}
                  WHERE bx.tag_id = {table_name}.id
                  {and_cond if values_and else ''}
                  AND Books.id = bx.book_id
                  {ex_cond if values_ex else ''}
                  GROUP BY Books.id
                  {and_count if values_and else ''}
                  ORDER BY {order_by}""", (*values_and, *values_ex, ))

    return c.fetchall()


def search_mult_assoc_col_int_ex(db_con, int_col_values_dict, ex_col_values_dict,
                                 order_by="Books.id DESC"):
    # nr of items in values multiplied is nr of rows returned needed to match
    # all conditions !! only include intersection vals
    mul_values = prod((len(vals) for vals in int_col_values_dict.values()))

    # containing table names for FROM .. stmt
    table_bridge_names = []
    # conditionals
    cond_statements = []
    # vals in order the stmts where inserted for sql param sub
    vals_in_order = []
    # build conditionals for select string
    for col, vals in int_col_values_dict.items():
        table_name, bridge_col_name = joined_col_name_to_query_names(col)
        table_bridge_names.append(table_name)
        table_bridge_names.append(f"Book{table_name}")

        cond_statements.append(f"{'AND' if cond_statements else 'WHERE'} "
                               f"Books.id = Book{table_name}.book_id")
        cond_statements.append(f"AND {table_name}.id = Book{table_name}.{bridge_col_name}")
        cond_statements.append(f"AND {table_name}.name IN ({','.join(['?']*len(vals))})")
        vals_in_order.extend(vals)
    for col, vals in ex_col_values_dict.items():
        table_name, bridge_col_name = joined_col_name_to_query_names(col)
        cond_statements.append(f"""
                 {'AND' if cond_statements else 'WHERE'} Books.id NOT IN (
                          SELECT Books.id
                          FROM Book{table_name} bx, Books, {table_name}
                          WHERE Books.id = bx.book_id
                          AND bx.{bridge_col_name} = {table_name}.id
                          AND {table_name}.name IN ({', '.join(['?']*len(vals))})
                )""")
        vals_in_order.extend(vals)

    table_bridge_names = ", ".join(table_bridge_names)
    cond_statements = "\n".join(cond_statements)

    c = db_con.execute(f"""
            SELECT Books.*
            FROM Books, {table_bridge_names}
            {cond_statements}
            GROUP BY Books.id HAVING COUNT(Books.id) = {mul_values}
            ORDER BY {order_by}""", (*vals_in_order,))
    return c.fetchall()


def search_assoc_col_string_parse(db_con,
                                  col,
                                  valuestring,
                                  delimiter=";",
                                  order_by="Books.id DESC"):
    # is list comprehension faster even though we have to iterate over the list twice?
    vals_and = []
    vals_ex = []
    # sort vals for search_tags_intersection_exclude func
    for val in valuestring.split(delimiter):
        if val[0] == "!":
            # remove ! then append
            vals_ex.append(val[1:])
        else:
            vals_and.append(val)

    return search_assoc_col_intersection_exclude(
                db_con,
                col,
                vals_and,
                vals_ex,
                order_by=order_by)


def search_equals_cols_values(db_con,
                              col_value_dict,
                              order_by="Books.id DESC"):
    """Searches for rows that match all the given values for the given rows
    col_name is not meant for user input -> should be validated b4 calling search_col_for_value
    usage: search_cols_for_values(conn, ("artist", "Enomoto Hidehira"),
                                 ("title_eng", "Papilla Heat Up Ch 1-2"))"""
    cond_statements = []
    vals_in_order = []
    for col, val in col_value_dict.items():
        cond_statements.append(f"{'AND' if cond_statements else 'WHERE'} {col} = ?")
        vals_in_order.append(val)
    cond_statements = "\n".join(cond_statements)

    c = db_con.execute(f"""
                SELECT * FROM Books
                {cond_statements}
                ORDER BY {order_by}""", (*vals_in_order, ))

    return c.fetchall()


def search_like_cols_values(db_con,
                            col_value_dict,
                            order_by="Books.id DESC"):
    """Searches for rows that contain all the values for all the given rows
    col_name is not meant for user input -> should be validated b4 calling search_col_for_value
    usage: search_cols_for_values(conn, {"artist": "Enomoto Hidehira",
                                         "title_eng": "Papilla Heat Up Ch 1-2"})"""
    cond_statements = []
    vals_in_order = []
    for col, val in col_value_dict.items():
        cond_statements.append(f"{'AND' if cond_statements else 'WHERE'} {col} LIKE ?")
        vals_in_order.append(f"%{val}%")
    cond_statements = "\n".join(cond_statements)

    c = db_con.execute(f"""
                SELECT * FROM Books
                {cond_statements}
                ORDER BY {order_by}""", (*vals_in_order, ))

    return c.fetchall()


VALID_ORDER_BY = ("ASC", "DESC", "Books.id", "Books.title_eng",
                  "Books.pages", "Books.my_rating", "Books.last_change")


def validate_order_by_str(order_by):
    for part in order_by.split(" "):
        if part not in VALID_ORDER_BY:
            return False
    return True


def search_book_by_title(db_con,
                         title,
                         order_by="Books.id DESC"):
    # search title or title_eng?
    # '%?%' doesnt work since ' disable ? and :name as placeholder
    # You should use query parameters where possible, but query parameters can't be used to
    # supply table and column names or keywords.
    # In this case you need to use plain string formatting to build your query. If your
    # parameters (in this case sort criterium and order) come from user input you need to
    # validate it first
    c = db_con.execute(f"""
                  SELECT * FROM Books
                  WHERE title LIKE ?
                  ORDER BY {order_by}""", (f"%{title}%", ))

    return c.fetchall()
