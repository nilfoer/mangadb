from functools import reduce
import operator

UNESCAPED, ESCAPED = 0, 1


def escape_string(string, escape_char="\\", to_escape=(",")):
    if not string:
        return string
    result = string
    for char_to_escape in to_escape:
        result = result.replace(char_to_escape, escape_char+char_to_escape)
    return result


def unescape_string(string, escape_char="\\"):
    if not string:
        return string
    state = UNESCAPED
    result = ""
    for c in string:
        if state == ESCAPED:
            # if we had more special chars we could handle them here
            result += c
            # escape is only for one char (unlike quotes) -> reset to unescaped
            state = UNESCAPED
        else:
            if c == escape_char:
                state = ESCAPED
            else:
                result += c
    return result

def list_to_string(li, escape_char="\\", sep=","):
    # cant save [] in db and need to preserve NULL in db -> None
    if li is None:
        return None
    return sep.join(("".join((c if c != sep else escape_char + c for c in string)) if string else string for string in li))


def string_to_list(string, escape_char="\\", sep=","):
    if string is None:
        return None
    result = []
    state = UNESCAPED
    current_item = ""
    for c in string:
        if state == ESCAPED:
            # if we had more special chars we could handle them here
            current_item += c
            # escape is only for one char (unlike quotes) -> reset to unescaped
            state = UNESCAPED
        else:
            if c == escape_char:
                state = ESCAPED
            elif c == sep:
                result.append(current_item)
                current_item = ""
            else:
                current_item += c
    result.append(current_item)
    return result


def print_sqlite3_row(row, sep=";"):
    str_li = []
    for key in row.keys():
        str_li.append(f"{key}: {row[key]}")
    print(sep.join(str_li))


def joined_col_name_to_query_names(col_name):
    # TODO mb to Book cls and validate col name
    # have to be careful not to use user input e.g. col_name in SQL query
    # without passing them as params to execute etc.
    table_name = col_name.capitalize()
    bridge_col_name = f"{col_name}_id"
    if bridge_col_name == "groups_id":
        bridge_col_name = "group_id"
    return table_name, bridge_col_name


def prod(iterable):
    return reduce(operator.mul, iterable, 1)
