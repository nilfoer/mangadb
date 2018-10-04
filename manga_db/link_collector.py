import pyperclip


class LinkCollector:
    pass


def watch_clip_db_get_info_after(db_book_ids,
                                 fixed_lists=None,
                                 predicate=is_tsu_book_url):
    found = []
    print("Available copy cmds are: set_tags, remove_book !")
    try:
        logger.info("Watching clipboard...")
        # upd_setting -> should we update Book; upd_all -> print update prompt
        upd_setting, upd_all = None, None
        recent_value = ""
        while True:
            tmp_value = pyperclip.paste()
            if tmp_value != recent_value:
                recent_value = tmp_value
                # if predicate is met
                if predicate(recent_value):
                    logger.info("Found manga url: \"%s\"", recent_value)
                    if book_id_from_url(recent_value) in db_book_ids:
                        upd = True
                        if upd_all:
                            if upd_setting:
                                logger.info(
                                    "Book was found in db and will be updated!"
                                )
                            else:
                                logger.info(
                                    "Book was found in db and will not be updated!"
                                )
                        else:
                            logger.info("Book was found in db!")

                        if upd_setting is None or not upd_all:
                            if not found:
                                print(
                                    "Selected lists will ONLY BE ADDED, no list "
                                    "will be removed!")
                            inp_upd_setting = input(
                                "Should book in DB be updated? "
                                "y/n/all/none:\n")
                            if inp_upd_setting == "n":
                                upd_setting = False
                                print("Book will NOT be updated!")
                            elif inp_upd_setting == "all":
                                upd_setting = True
                                upd_all = True
                                print("All books will be updated!")
                            elif inp_upd_setting == "none":
                                upd_setting = False
                                upd_all = True
                                print("No books will be updated!")
                            else:
                                upd_setting = True
                                print("Book will be updated!")
                    else:
                        upd = False

                    # only append to list if were not updating or upd_setting -> True
                    if not upd or upd_setting:
                        if fixed_lists is None:
                            manga_lists = enter_manga_lists(len(found))
                            # strip urls of trailing "-" since there is a dash appended to
                            # the url when exiting from reading a manga on tsumino (compared
                            # to when entering from main site)
                            found.append((recent_value.rstrip("-"),
                                          manga_lists, upd))
                        else:
                            found.append((recent_value.rstrip("-"),
                                          fixed_lists, upd))
                elif recent_value == "set_tags":
                    url, tag_li, upd = found.pop()
                    logger.info(
                        "Setting tags for \"%s\"! Previous tags were: %s", url,
                        tag_li)
                    manga_lists = enter_manga_lists(len(found) - 1)
                    found.append((url, manga_lists, upd))
                elif recent_value == "remove_book":
                    logger.info("Deleted last book with url \"%s\" from list",
                                found[-1][0])
                    del found[-1]

            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Stopped watching clipboard!")

    # use filter_duplicate_at_index_of_list_items to only keep latest list element with same
    # urls -> index 0 in tuple
    return filter_duplicate_at_index_of_list_items(0, found)


def write_resume_info(filename, info):
    info_str = "\n".join(
        (f"{tup[0]};{','.join(tup[1])};{tup[2]}" for tup in info))

    with open(filename, "w", encoding="UTF-8") as w:
        w.write(info_str)


def resume_from_file(filename):
    with open("resume_info.txt", "r", encoding="UTF-8") as f:
        info = f.read().splitlines()

    result = []
    for ln in info:
        url, tags, upd = ln.split(";")
        upd = True if upd == "True" else False
        result.append((url, tags.split(","), upd))

    return result


