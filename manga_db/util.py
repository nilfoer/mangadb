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
