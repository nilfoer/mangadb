def write_to_txtf(wstring, filename):
    """
    Writes wstring to filename

    :param wstring: String to write to file
    :param filename: Path/Filename
    :return: None
    """
    with open(filename, "w", encoding="UTF-8") as w:
        w.write(wstring)
