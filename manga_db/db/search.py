import logging

from .util import joined_col_name_to_query_names, prod

logger = logging.getLogger(__name__)


def search_assoc_col_string_parse(valuestring, delimiter=";"):
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

    return vals_and, vals_ex


VALID_ORDER_BY = ("ASC", "DESC", "Books.id", "Books.title_eng", "Books.title_foreign",
                  "Books.pages", "Books.my_rating", "Books.last_change")


def validate_order_by_str(order_by):
    for part in order_by.split(" "):
        if part not in VALID_ORDER_BY:
            return False
    return True


def search_book_by_title(db_con,
                         title,
                         order_by="Books.id DESC",
                         limit=-1, last_id=None):
    # search title or title_eng?
    # '%?%' doesnt work since ' disable ? and :name as placeholder
    # You should use query parameters where possible, but query parameters can't be used to
    # supply table and column names or keywords.
    # In this case you need to use plain string formatting to build your query. If your
    # parameters (in this case sort criterium and order) come from user input you need to
    # validate it first
    title_wildcarded = f"%{title}%"
    vals_in_order = [title_wildcarded, title_wildcarded]
    if last_id is not None:
        keyset_pagination = f"AND id {'<' if order_by.endswith('DESC') else '>'} ?"
        vals_in_order.append(last_id)
    else:
        keyset_pagination = ""

    c = db_con.execute(f"""
                  SELECT * FROM Books
                  WHERE title_eng LIKE ?
                  OR title_foreign LIKE ?
                  {keyset_pagination}
                  ORDER BY {order_by}
                  LIMIT ?""", (*vals_in_order, limit))
    rows = c.fetchall()

    return rows


def search_normal_mult_assoc(
        db_con, normal_col_values, int_col_values_dict, ex_col_values_dict,
        order_by="Books.id DESC", limit=-1,  # no row limit when limit is neg. nr
        after=None, before=None):
    """Can search in normal columns as well as multiple associated columns
    (connected via bridge table) and both include and exclude them"""
    # @Cleanup mb split into multiple funcs that just return the conditional string
    # like: WHERE title LIKE ? and the value, from_table_names etc.?

    if int_col_values_dict:
        # nr of items in values multiplied is nr of rows returned needed to match
        # all conditions !! only include intersection vals
        mul_values = prod((len(vals) for vals in int_col_values_dict.values()))
        assoc_incl_cond = f"GROUP BY Books.id HAVING COUNT(Books.id) = {mul_values}"
    else:
        assoc_incl_cond = ""

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

    # normal col conditions
    for col, val in normal_col_values.items():
        # use pattern match for title
        if "title" in col:
            title_wildcarded = f"%{val}%"
            cond_statements.append(
                    f"{'AND' if cond_statements else 'WHERE'} (Books.title_eng LIKE ? "
                    "OR Books.title_foreign LIKE ?)")
            vals_in_order.extend([title_wildcarded]*2)
        else:
            cond_statements.append(f"{'AND' if cond_statements else 'WHERE'} Books.{col} = ?")
            vals_in_order.append(val)

    table_bridge_names = ", ".join(table_bridge_names)
    cond_statements = "\n".join(cond_statements)

    query = f"""
            SELECT Books.*
            FROM Books{',' if table_bridge_names else ''} {table_bridge_names}
            {cond_statements}
            {assoc_incl_cond}
            ORDER BY {order_by}
            LIMIT ?"""
    # important to do this last and limit mustnt be in vals_in_order (since its after
    # keyset param in sql substitution)
    query, vals_in_order = keyset_pagination_statment(
            query, vals_in_order, after=after, before=before,
            order_by=order_by, first_cond=not bool(cond_statements)
            )
    c = db_con.execute(query, (*vals_in_order, limit))
    rows = c.fetchall()

    return rows


def keyset_pagination_statment(query, vals_in_order, after=None, before=None,
                               order_by="Books.id DESC", first_cond=False):
    """Finalizes query by inserting keyset pagination statement
    Must be added/called last!
    !! Assumes SQL statements are written in UPPER CASE !!
    :param query: Query string
    :param vals_in_order: List of values that come before id after/before in terms of parameter
                          substitution; Might be None if caller wants to handle it himself
    :return: Returns finalized query and vals_in_order"""
    # CAREFUL order_by needs to be unique for keyset pagination, possible to add rnd cols
    # to make it unique
    if after is not None and before is not None:
        raise ValueError("Either after or before can be supplied but not both!")
    elif after is None and before is None:
        return query, vals_in_order

    result = None
    # contrary to split partition returns list with the elements that were split on included
    asc = True if order_by.lower().endswith("asc") else False
    if after is not None:
        comp = ">" if asc else "<"
    else:
        comp = "<" if asc else ">"

    # @Cleanup assuming upper case ORDER BY
    lines = [l.strip() for l in query.splitlines()]
    insert_before = [i for i, l in enumerate(lines) if l.startswith("GROUP BY") or
                     l.startswith("ORDER BY")][0]
    keyset_pagination = f"{'WHERE' if first_cond else 'AND'} Books.id {comp} ?"
    lines.insert(insert_before, keyset_pagination)
    result = "\n".join(lines)
    if vals_in_order is not None:
        vals_in_order.append(after if after is not None else before)

    if before is not None:
        # @Cleanup assuming upper case order statment
        # need to reverse order in query to not get results starting from first one possible
        # to before(id) but rather to get limit nr of results starting from before(id)
        result = result.replace(f"{' ASC' if asc else ' DESC'}", f"{' DESC' if asc else ' ASC'}")
        result = f"""
            SELECT *
            FROM (
                {result}
            ) AS t
            ORDER BY {order_by.replace('Books', 't', 1)}"""

    return result, vals_in_order
