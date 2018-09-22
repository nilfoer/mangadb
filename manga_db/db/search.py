import re
import logging
import sqlite3

logger = logging.getLogger(__name__)


def search_tags_intersection(db_con,
                             tags,
                             order_by="Tsumino.id DESC",
                             keep_row_fac=False):
    """Searches for entries containing all tags in tags and returns the rows as
    a list of sqlite3.Row objects
    :param db_con: Open connection to database
    :param tags: List of tags as strings
    :return List of sqlite3.Row objects"""

    # would also be possible to use c.description but as i want to populate a dictionary
    # anyways Row is a better fit
    # Row provides both index-based and case-insensitive name-based access to columns with
    # almost no memory overhead
    db_con.row_factory = sqlite3.Row
    # we need to create new cursor after changing row_factory
    c = db_con.cursor()

    # even though Row class can be accessed both by index (like tuples) and
    # case-insensitively by name
    # reset row_factory to default so we get normal tuples when fetching (should we
    # generate a new cursor)
    # new_c will always fetch Row obj and cursor will fetch tuples
    # -> this was generating problems when called from webGUI that always expected Rows
    # since we set it there in the module, but calling the search_tags_.. functions always
    # reset it back to tuples
    if not keep_row_fac:
        db_con.row_factory = None

    # dynamically insert correct nr (as many ? as elements in tags) of ? in SQLite
    # query using join on ", " and ["?"] * amount
    # then unpack list with arguments using *tags

    # SQLite Query -> select alls columns in Tsumino
    # tagids must match AND name of the tag(singular) must be in tags list
    # bookids must match
    # results are GROUPed BY Tsumino.id and only entries are returned that occur
    # ? (=nr of tags in tags) times --> matching all tags
    c.execute(f"""SELECT Tsumino.*
                  FROM BookTags bt, Tsumino, Tags
                  WHERE bt.tag_id = Tags.tag_id
                  AND (Tags.name IN ({', '.join(['?']*len(tags))}))
                  AND Tsumino.id = bt.book_id
                  GROUP BY Tsumino.id
                  HAVING COUNT( Tsumino.id ) = ?
                  ORDER BY {order_by}""", (*tags, len(tags)))

    return c.fetchall()


def search_tags_exclude(db_con,
                        tags,
                        order_by="Tsumino.id DESC",
                        keep_row_fac=False):
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    if not keep_row_fac:
        db_con.row_factory = None
    # select all tsumino.ids that contain these tags (OR, would be AND with HAVING COUNT)
    # -> select all rows whose ids are not in the sub-query
    c.execute(f"""SELECT Tsumino.*
                  FROM Tsumino
                  WHERE Tsumino.id NOT IN (
                          SELECT Tsumino.id
                          FROM BookTags bt, Tsumino, Tags
                          WHERE Tsumino.id = bt.book_id
                          AND bt.tag_id = Tags.tag_id
                          AND Tags.name IN ({', '.join(['?']*len(tags))})
                )
                ORDER BY {order_by}""", (*tags, ))
    # ^^ use *tags, -> , to ensure its a tuple when only one tag supplied

    return c.fetchall()


def search_tags_intersection_exclude(db_con,
                                     tags_and,
                                     tags_ex,
                                     order_by="Tsumino.id DESC",
                                     keep_row_fac=False):
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    if not keep_row_fac:
        db_con.row_factory = None

    c.execute(f"""SELECT Tsumino.*
                  FROM BookTags bt, Tsumino, Tags
                  WHERE bt.tag_id = Tags.tag_id
                  AND (Tags.name IN ({', '.join(['?']*len(tags_and))}))
                  AND Tsumino.id = bt.book_id
                  AND Tsumino.id NOT IN (
                    SELECT Tsumino.id
                    FROM BookTags bt, Tsumino, Tags
                    WHERE Tsumino.id = bt.book_id
                    AND bt.tag_id = Tags.tag_id
                    AND Tags.name IN ({', '.join(['?']*len(tags_ex))})
                  )
                  GROUP BY Tsumino.id
                  HAVING COUNT( Tsumino.id ) = ?
                  ORDER BY {order_by}""", (*tags_and, *tags_ex, len(tags_and)))

    return c.fetchall()


def search_tags_string_parse(db_con,
                             tagstring,
                             order_by="Tsumino.id DESC",
                             keep_row_fac=False):
    if "!" in tagstring:
        excl_nr = tagstring.count("!")
        # nr of commas + 1 == nr of tags
        tags_nr = tagstring.count(",") + 1
        if tags_nr == excl_nr:
            tags = [tag[1:] for tag in tagstring.split(",")]
            # only excluded tags in tagstring
            return search_tags_exclude(
                db_con, tags, order_by=order_by, keep_row_fac=keep_row_fac)
        else:
            # is list comprehension faster even though we have to iterate over the list twice?
            tags_and = []
            tags_ex = []
            # sort tags for search_tags_intersection_exclude func
            for tag in tagstring.split(","):
                if tag[0] == "!":
                    # remove ! then append
                    tags_ex.append(tag[1:])
                else:
                    tags_and.append(tag)

            return search_tags_intersection_exclude(
                db_con,
                tags_and,
                tags_ex,
                order_by=order_by,
                keep_row_fac=keep_row_fac)
    else:
        tags = tagstring.split(",")
        return search_tags_intersection(
            db_con, tags, order_by=order_by, keep_row_fac=keep_row_fac)


VALID_SEARCH_TYPES = ("tags", "title", "artist", "collection", "groups",
                      "character")
# part of lexical analysis
# This expression states that a "word" is either (1) non-quote, non-whitespace text
# surrounded by whitespace, or (2) non-quote text surrounded by quotes (followed by some
# whitespace).
WORD_RE = re.compile(r'([^"^\s]+)\s*|"([^"]+)"\s*')


def search_sytnax_parser(db_con,
                         search_str,
                         order_by="Tsumino.id DESC",
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
        order_by = "Tsumino.id DESC"

    if search_str:
        return search_book(db_con, order_by=order_by, **search_options)
    else:
        return get_all_books(db_con, order_by=order_by, **search_options)


def get_all_books(db_con, order_by="Tsumino.id DESC", keep_row_fac=False):
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    if not keep_row_fac:
        db_con.row_factory = None

    c.execute(f"""SELECT * FROM Tsumino
                  ORDER BY {order_by}""")

    return c.fetchall()


def search_book(db_con,
                order_by="Tsumino.id DESC",
                keep_row_fac=False,
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
        order_by_col = order_by.split(" ")[0].replace("Tsumino.", "")
        result = sorted(result, key=lambda x: x[order_by_col])
        if " DESC" in order_by:
            # sorted orders ascending (at least for chars and numbers) -> reverse for DESC
            result = reversed(result)
    else:
        result = result_row_lists[0]

    return result


def search_equals_cols_values(db_con,
                              *col_name_value_pairs,
                              order_by="Tsumino.id DESC",
                              keep_row_fac=False):
    """Searches for rows that match all the given values for the given rows
    col_name is not meant for user input -> should be validated b4 calling search_col_for_value
    usage: search_cols_for_values(conn, ("artist", "Enomoto Hidehira"),
                                 ("title_eng", "Papilla Heat Up Ch 1-2"))"""
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    if not keep_row_fac:
        db_con.row_factory = None

    col_name, value = col_name_value_pairs[0]
    if len(col_name_value_pairs) > 1:
        col_names = [f"{col_n} = ?" for col_n, _ in col_name_value_pairs[1:]]
        values = [tup[1] for tup in col_name_value_pairs[1:]]
    else:
        col_names, values = [], []

    c.execute(f"""SELECT * FROM Tsumino
                  WHERE {col_name} = ? {"AND " if len(col_name_value_pairs) > 1 else ""}{" AND ".join(col_names)}
                  ORDER BY {order_by}""", (value, *values))

    return c.fetchall()


def search_like_cols_values(db_con,
                            *col_name_value_pairs,
                            order_by="Tsumino.id DESC",
                            keep_row_fac=False):
    """Searches for rows that contain all the values for all the given rows
    col_name is not meant for user input -> should be validated b4 calling search_col_for_value
    usage: search_cols_for_values(conn, ("artist", "Enomoto Hidehira"),
                                 ("title_eng", "Papilla Heat Up Ch 1-2"))"""
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    if not keep_row_fac:
        db_con.row_factory = None

    col_name, value = col_name_value_pairs[0]
    if len(col_name_value_pairs) > 1:
        col_names = [
            f"{col_n} LIKE ?" for col_n, _ in col_name_value_pairs[1:]
        ]
        values = [f"%{tup[1]}%" for tup in col_name_value_pairs[1:]]
    else:
        col_names, values = [], []

    c.execute(f"""SELECT * FROM Tsumino
                  WHERE {col_name} LIKE ? {"AND " if len(col_name_value_pairs) > 1 else ""}{" AND ".join(col_names)}
                  ORDER BY {order_by}""", (f"%{value}%", *values))

    return c.fetchall()


VALID_ORDER_BY = ("ASC", "DESC", "Tsumino.id", "Tsumino.title_eng",
                  "Tsumino.upload_date", "Tsumino.pages", "Tsumino.rating",
                  "Tsumino.my_rating", "Tsumino.last_change")


def validate_order_by_str(order_by):
    for part in order_by.split(" "):
        if part not in VALID_ORDER_BY:
            return False
    return True


def search_book_by_title(db_con,
                         title,
                         order_by="Tsumino.id DESC",
                         keep_row_fac=False):
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    if not keep_row_fac:
        db_con.row_factory = None

    # search title or title_eng?
    # '%?%' doesnt work since ' disable ? and :name as placeholder
    # You should use query parameters where possible, but query parameters can't be used to
    # supply table and column names or keywords.
    # In this case you need to use plain string formatting to build your query. If your
    # parameters (in this case sort criterium and order) come from user input you need to
    # validate it first
    c.execute(f"""SELECT * FROM Tsumino
                  WHERE title LIKE ?
                  ORDER BY {order_by}""", (f"%{title}%", ))

    return c.fetchall()
