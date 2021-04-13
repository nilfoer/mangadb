import logging

from typing import List, Dict, Tuple, Optional

from .util import joined_col_name_to_query_names, prod

logger = logging.getLogger(__name__)


def search_assoc_col_string_parse(valuestring, delimiter=";") -> Tuple[List[str], List[str]]:
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


VALID_ORDER_BY = {"ASC", "DESC", "Books.id", "Books.title_eng", "Books.title_foreign",
                  "Books.pages", "Books.my_rating", "Books.last_change", "id", "last_change",
                  "title_eng", "title_foreign", "pages", "my_rating"}


def validate_order_by_str(order_by) -> bool:
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
        db_con, normal_col_values: Dict[str, str], int_col_values_dict: Dict[str, List[str]],
        ex_col_values_dict: Dict[str, List[str]], order_by: str = "Books.id DESC",
        limit: int = -1,  # no row limit when limit is neg. nr
        # TODO type prob incorrect since sometimes (13,) is passed etc.
        after: Optional[Tuple[str, str]] = None,
        before: Optional[Tuple[str, str]] = None):
    """Can search in normal columns as well as multiple associated columns
    (connected via bridge table) and both include and exclude them
    :param normal_col_values: Dict that maps column names to search value
    :param int_col_values: Dict that maps column names to search value
    """
    # @Cleanup mb split into multiple funcs that just return the conditional string
    # like: WHERE title LIKE ? and the value, from_table_names etc.?
    # @Cleanup convert this to use joins

    grp_by: List[str] = []
    having: List[str] = []
    if int_col_values_dict:
        # nr of items in values multiplied is nr of rows returned needed to match
        # all conditions !! only include intersection vals
        mul_values = prod((len(vals) for vals in int_col_values_dict.values()))
        grp_by.append("Books.id")
        having.append(f"COUNT(Books.id) = {mul_values}")

    # containing table names for FROM .. stmt
    table_bridge_names: List[str] = []
    # conditionals
    cond_statements: List[str] = []
    # vals in order the stmts where inserted for sql param sub
    vals_in_order: List[str] = []
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
        if col.startswith("title"):
            title_wildcarded = f"%{val}%"
            cond_statements.append(
                    f"{'AND' if cond_statements else 'WHERE'} (Books.title_eng LIKE ? "
                    "OR Books.title_foreign LIKE ?)")
            vals_in_order.extend([title_wildcarded]*2)
        elif col == "read_status":
            # TODO include chapter_status?
            if val == "read":
                read_cond = "= 0"
            elif val == "unread":
                read_cond = "IS NULL"
            else:
                read_cond = "> 0"

            cond_statements.append(
                    f"{'AND' if cond_statements else 'WHERE'} Books.read_status {read_cond}")
        elif col == "downloaded":
            # need to use a separate subquery for this since joining with ExternalInfo
            # in order to check ei.downloaded where we use having sum(ei.downloaded) > 0
            # to check if a book counts as dled, gets mixed up with checking the counts
            # for having the correct number of assoc values present for int_col_values
            cond_statements.append(f"""
                {'AND' if cond_statements else 'WHERE'}
                (
                    SELECT count(*) FROM ExternalInfo ei
                    WHERE ei.book_id = Books.id
                    AND ei.downloaded > 0
                ) {'=' if val == '0' else '>'} 0""")
        else:
            cond_statements.append(f"{'AND' if cond_statements else 'WHERE'} Books.{col} = ?")
            vals_in_order.append(val)

    table_bridge_names_str = ", ".join(table_bridge_names)
    cond_statements_str = "\n".join(cond_statements)

    query = [
        "SELECT Books.*",
        f"FROM Books{',' if table_bridge_names_str else ''} {table_bridge_names_str}",
    ]
    query.append(cond_statements_str)
    if grp_by:
        query.append(f"GROUP BY {', '.join(grp_by)}")
    if having:
        query.append(f"HAVING {' AND '.join(having)}")
    query.append(f"ORDER BY {order_by}")
    query.append("LIMIT ?")

    # important to do this last and limit mustnt be in vals_in_order (since its after
    # keyset param in sql substitution)
    final_query, vals_in_order = keyset_pagination_statment(
            query, vals_in_order, after=after, before=before,
            order_by=order_by, first_cond=not bool(cond_statements)
            )
    print(final_query)
    c = db_con.execute(final_query, (*vals_in_order, limit))
    rows = c.fetchall()

    return rows


def insert_order_by_id(query: List[str], order_by="Books.id DESC") -> str:
    # !! Assumes SQL statements are written in UPPER CASE !!
    # also sort by id secondly so order by is unique (unless were already using id)
    if "books.id" not in order_by.lower():
        # if we have subqueries take last order by to insert; strip line of whitespace since
        # we might have indentation
        order_by_i = [i for i, ln in enumerate(query) if ln.strip().startswith("ORDER BY")][-1]
        inserted = f"ORDER BY {order_by}, {order_by.split('.')[0]}.id {order_by.split(' ')[1]}"
        query[order_by_i] = inserted
        result = "\n".join(query)
    else:
        result = "\n".join(query)
    return result


def keyset_pagination_statment(query: List[str], vals_in_order: List[str],
                               after: Optional[Tuple[str, str]] = None,
                               before: Optional[Tuple[str, str]] = None,
                               order_by="Books.id DESC", first_cond=False):
    """Finalizes query by inserting keyset pagination statement
    Must be added/called last!
    !! Assumes SQL statements are written in UPPER CASE !!
    :param query: Query string
    :param vals_in_order: List of values that come before id after/before in terms of parameter
                          substitution; Might be None if caller wants to handle it himself
    :param order_by: primary column to sort by and the sorting order e.g. Books.id DESC
    :param first_cond: If the clause were inserting will be the first condition in the statment
    :return: Returns finalized query and vals_in_order"""
    # CAREFUL order_by needs to be unique for keyset pagination, possible to add rnd cols
    # to make it unique
    if after is not None and before is not None:
        raise ValueError("Either after or before can be supplied but not both!")
    elif after is None and before is None:
        return insert_order_by_id(query, order_by), vals_in_order

    asc = True if order_by.lower().endswith("asc") else False
    if after is not None:
        comp = ">" if asc else "<"
    else:
        comp = "<" if asc else ">"

    # @Cleanup assuming upper case sqlite statements
    insert_before = [i for i, l in enumerate(query) if l.startswith("GROUP BY") or
                     l.startswith("ORDER BY")][0]
    un_unique_sort_col = "books.id" not in order_by.lower()
    if un_unique_sort_col:
        order_by_col = order_by.split(' ')[0]
        # 2-tuple of (primary, secondary)
        # casting to non-null didn't work so have to ignore here
        primary, secondary = after if after is not None else before  # type: ignore
        # if primary is NULL we need IS NULL as "equals comparison operator" since
        # normal comparisons with NULL are always False
        if primary is None:
            equal_comp = "IS NULL"
        else:
            equal_comp = "== ?"
        # for ASCENDING order:
        # slqite sorts NULLS first by default -> when e.g. going forwards in ASC order
        # and we have a NULL value for primary sorting col as last row/book on page
        # we need to include IS NOT NULL condition so we include rows with not-null values
        # if the NULL isnt the last row/book we can go forward normallly
        # if we go backwards we always need to include OR IS NULL since there might be a
        # NULL on the next page
        # if the NULL is first on the page then we need IS NULL and compare the id
        # other way around for DESC order
        # also other way around if sqlite sorted NULLs last (we could also emulate that with
        # ORDER BY (CASE WHEN null_column IS NULL THEN 1 ELSE 0 END) ASC, primary ASC, id ASC)

        # longer but more explicit if clauses
        # if before is not None:
        #     if asc:
        #         # include NULLs when going backwards unless we already had a NULL on the page
        #         null_clause = f"OR ({order_by_col} IS NULL)" if primary is not None else ""
        #     else:
        #         # include NOT NULLs when going backwards unless we already had a
        #         # NOT NULL on the page
        #         null_clause = f"OR ({order_by_col} IS NOT NULL)" if primary is None else ""
        # else:
        #     if asc:
        #         # include NULLs when going forwards unless we already had a NOT NULL on the page
        #         null_clause = f"OR ({order_by_col} IS NOT NULL)" if primary is None else ""
        #     else:
        #         # include NULLs when going forwards unless we already had a NULL on the page
        #         null_clause = f"OR ({order_by_col} IS NULL)" if primary is not None else ""
        if (before is not None and asc) or (after is not None and not asc):
            # ASC: include NULLs when going backwards unless we already had a NULL on the page
            # DESC: include NULLs when going forwards unless we already had a NULL on the page
            null_clause = f"OR ({order_by_col} IS NULL)" if primary is not None else ""
        elif (before is not None and not asc) or (after is not None and asc):
            # ASC: include NULLs when going forwards unless we already had a NOT NULL on the page
            # DESC: include NOT NULLs when going backwards unless we already had a
            #       NOT NULL on the page
            null_clause = f"OR ({order_by_col} IS NOT NULL)" if primary is None else ""

        # since we sort by both the primary order by and the id to make the sort unique
        # we need to check for rows matching the value of the sort col -> then we use the id to
        # have a correct sort
        # parentheses around the whole statement important otherwise rows fullfilling the OR
        # statement will get included when searching even if they dont fullfill the rest
        keyset_pagination = (f"{'WHERE' if first_cond else 'AND'} ({order_by_col} {comp} ? "
                             f"OR ({order_by_col} {equal_comp} AND Books.id {comp} ?) "
                             f"{null_clause})")
        # we only need primare 2 times if we compare by a value with ==
        vals_in_order.extend((primary, primary, secondary) if equal_comp.startswith("==")  # type: ignore
                             else (primary, secondary))
    else:
        keyset_pagination = f"{'WHERE' if first_cond else 'AND'} Books.id {comp} ?"
        # if vals_in_order is not None:
        vals_in_order.append(after[0] if after is not None else before[0])  # type: ignore
    query.insert(insert_before, keyset_pagination)

    if un_unique_sort_col:
        result = insert_order_by_id(query, order_by)
    else:
        result = "\n".join(query)

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
            ORDER BY {order_by.replace('Books.', 't.')}"""
        if un_unique_sort_col:
            # since were using a subquery we need to modify our order by to use the AS tablename
            # @Cleanup splitlines after we joined before
            result = insert_order_by_id(result.splitlines(), order_by.replace("Books.", "t."))

    return result, vals_in_order
