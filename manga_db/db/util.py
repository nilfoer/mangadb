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
