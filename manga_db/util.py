import re

def write_to_txtf(wstring, filename):
    """
    Writes wstring to filename

    :param wstring: String to write to file
    :param filename: Path/Filename
    :return: None
    """
    with open(filename, "w", encoding="UTF-8") as w:
        w.write(wstring)

def get_index_of_last_match(obj, li):
    """Get index of last item matching obj in list"""
    # start end step, start inclusive - end not
    for i in range(len(li) - 1, -1, -1):
        if obj == li[i]:
            return i

def filter_duplicate_at_index_of_list_items(i, li):
    # filter duplicates based on element at pos i in tuples only keeping latest entries in list
    # filter_elements = [t[i] for t in tuple_list]
    # i could either use get_index_of_last_match to get index of last occurrence of match in
    # filter_elements and in for loop check if were at that pos True->append False->continue (if count in filter_elements > 1)
    # -> would mean iterating/searching over list
    # (1 + (len(tuple_list) + len(tuple_list)) * len(tuple_list)
    # or reverse tuple_list, and keep track of items at pos i that were alrdy seen/added
    # tuple_list[i] alrdy seen -> continue
    items_at_i = set()
    result = []
    for tup in reversed(li):
        if tup[i] in items_at_i:
            continue
        else:
            result.append(tup)
            items_at_i.add(tup[i])
    # order not preserved, reversing again would be closer to old order
    return result

def test_filter_duplicate_at_index_of_list_items():
    l = [("abc", 0, 0), ("def", 1, 1), ("abc", 2, 2),
         ("ghi", 3, 3), ("def", 4, 4), ("jkl", 5, 5,)]
    res = filter_duplicate_at_index_of_list_items(0, l)
    return res == [('jkl', 5, 5), ('def', 4, 4), ('ghi', 3, 3), ('abc', 2, 2)]


# re.UNICODE is redundant in Python 3 since matches are Unicode by default for strings
# removed \u10000-\u1BC9F \u1D200-\u1D37F \u20000-\u2FA1FCJK 
# they somehow matched normal latin chars, mb becaus theyre too high a number
# but they appear in utf-8
FOREIGN_RE = re.compile(r"[\u0100-\u02AF\u0370-\u1CFF\u1F00−\u1FFF\u2C00-\u2DFF\u2E80-\uFDFF\uFE30−\uFE4F\uFE70−\uFEFF]")
# removed \u20000−\u2FA1FCJK
CJK_ASIAN_RE = re.compile(r"[\u2E80-\uA4CF\uA960−\uA97F\uAA00−\uAA5F\uAA60−\uAA7F\uAA80−\uAADF\uAAE0−\uAAFF\uAC00−\uD7AF\uD7B0−\uD7FF\uF900−\uFAFF\uFE30−\uFE4F]")


def contains_asian(string):
    if CJK_ASIAN_RE.search(string):
        return True
    else:
        return False


def contains_foreign(string):
    if FOREIGN_RE.search(string):
        return True
    else:
        return False


def count_asian_chars(string):
    return len(CJK_ASIAN_RE.findall(string))


def count_foreign_chars(string):
    return len(FOREIGN_RE.findall(string))


def is_asian(string, asian_chars_to_string_length=0.5):
    # findall returns each non-overlapping match in a list
    asian_char_amount = count_asian_chars(string)
    if asian_char_amount/len(string) >= asian_chars_to_string_length:
        return True
    else:
        return False


def is_foreign(string, foreign_chars_to_string_length=0.5):
    # findall returns each non-overlapping match in a list
    foreign_char_amount = count_foreign_chars(string)
    if foreign_char_amount/len(string) >= foreign_chars_to_string_length:
        return True
    else:
        return False
