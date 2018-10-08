import re
import logging
import sqlite3

from .util import joined_col_name_to_query_names, prod

logger = logging.getLogger(__name__)
VALID_SEARCH_COLS = {"title", "language", "status" "favorite",
                     "category", "artist", "parody", "character", "collection", "groups",
                     "tag", "list"}


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


# part of lexical analysis
# This expression states that a "word" is either (1) non-quote, non-whitespace text
# surrounded by whitespace, or (2) non-quote text surrounded by quotes (followed by some
# whitespace).
WORD_RE = re.compile(r'([^"^\s]+)\s*|"([^"]+)"\s*')


def search_sytnax_parser(manga_db,
                         search_str,
                         order_by="Books.id DESC",
                         **kwargs):
    search_options = kwargs
    # Return all non-overlapping matches of pattern in string, as a list of strings.
    # The string is scanned left-to-right, and matches are returned in the order found.
    # If one or more groups are present in the pattern, return a list of groups; this will
    # be a list of tuples if the pattern has more than one group. Empty matches are included
    # in the result.
    current_search_obj = None
    for match in re.findall(WORD_RE, search_str):
        single, multi_word = match
        part = None
        if single and ":" in single:
            # -> search type is part of the word
            search_type, part = single.split(":", 1)
            if search_type in VALID_SEARCH_TYPES:
                current_search_obj = search_type
            else:
                # set to None so we skip adding search_options for next word (which
                # still belongs to unsupported search_type)
                current_search_obj = None
                logger.info("%s is not a supported search type!", search_type)
                continue
        if not part:
            # a or b -> uses whatever var is true -> both true (which cant happen here) uses
            # first one
            part = single or multi_word
        # current_search_obj is None if search_type isnt supported
        # then we want to ignore this part of the search
        if current_search_obj:
            search_options[current_search_obj] = part

    # validate order_by from user input
    if not validate_order_by_str(order_by):
        logger.warning("Sorting %s is not supported", order_by)
        order_by = "Books.id DESC"

    if search_str:
        return search_book(manga_db, order_by=order_by, **search_options)
    else:
        return manga_db.get_x_books(order_by=order_by, **search_options)


def search_book(manga_db,
                order_by="Books.id DESC",
                **search_options):
    """Assumes AND condition for search_types, OR etc. not supported (and also not planned!)"""
    result_row_lists = []
    col_name_value_pairs = []
    for search_type, value in search_options.items():
        if search_type not in VALID_SEARCH_TYPES:
            logger.warning(
                "%s is not a valid search type! It shouldve been filtered out!",
                search_type)
        elif search_type == "tags":
            result_row_lists.append(
                search_tags_string_parse(
                    db_con,
                    value,
                    order_by=order_by,
                    keep_row_fac=keep_row_fac))
            continue
        col_name_value_pairs.append((search_type, value))

    if col_name_value_pairs:
        # could be multiple artists, groups etc. (in cell separated by ",") -> use like
        # for everything
        result_row_lists.append(
            search_like_cols_values(
                db_con,
                *col_name_value_pairs,
                order_by=order_by,
                keep_row_fac=keep_row_fac))

    # check if we have more than one search result that we need to intersect and then resort
    if len(result_row_lists) > 1:
        # now get intersection (ids must be present in all row lists) of result_row_lists:
        id_sets = []
        for row_list in result_row_lists:
            ids = set((row["id"] for row in row_list))
            id_sets.append(ids)
        # call intersection on (type)set directly so we can just pass in and unpack list of sets
        ids_intersect = set.intersection(*id_sets)

        result = []
        row_ids_in_result = set()
        for row_list in result_row_lists:
            # get rows that match all criteria (id is in ids_intersect)
            for row in row_list:
                # only append once
                if row["id"] not in row_ids_in_result and row["id"] in ids_intersect:
                    result.append(row)
                    row_ids_in_result.add(row["id"])

        # sort the result
        order_by_col = order_by.split(" ")[0].replace("Books.", "")
        result = sorted(result, key=lambda x: x[order_by_col])
        if " DESC" in order_by:
            # sorted orders ascending (at least for chars and numbers) -> reverse for DESC
            result = reversed(result)
    else:
        result = result_row_lists[0]

    return result


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
