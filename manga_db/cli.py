import sys
import argparse

from .webGUI.webGUI import main as start_webgui
from .manga_db import MangaDB
#from .link_collector import LinkCollector


def main():
    parser = argparse.ArgumentParser(description="Command-line interface for MangaDB - A "
                                     "database to keep track of your manga reading habits!")

    parser.add_argument("-db", "--db-path", default="manga_db.sqlite", type=str,
                        help="Path to db file; Default uses file named 'manga_db.sqlite' "
                        "in current working directory")
    subparsers = parser.add_subparsers(title='subcommands', description='valid subcommands',
                                       help='sub-command help', dest="subcmd")

    webgui = subparsers.add_parser("webgui", aliases=["web"])
    webgui.set_defaults(func=start_webgui)

    collector = subparsers.add_parser("link_collector", aliases=["collect"])
    collector.set_defaults(func=_cl_collector)

    export = subparsers.add_parser("export", aliases=["exp"])
    export.add_argument("path", type=str, help="Path/Filename of csv file the db should be "
                        "exported to")
    collector.set_defaults(func=_cl_export)

    args = parser.parse_args()
    if len(sys.argv) == 1:
        # default to stdout, but stderr would be better (use sys.stderr, then exit(1))
        parser.print_help()
        sys.exit(0)
    args.func(args)

    hstr = """OPTIONS:    [watch] Watch clipboard for manga urls, get and write info afterwards
    [resume] Resume from crash
    [rate] url rating: Update rating for book with supplied url
    [exportcsv] Export csv-file of SQLite-DB
    [search_tags] \"tag,!exclude_tag,..\": Returns title and url of books with matching tags
    [search_title] title: Prints title and url of books with matching title
    [add_book] \"tag1,tag2,..\" url (writeinfotxt): Adds book with added tags to db using url
    [update_book] \"tag1,tag2,..\" url (writeinfotxt): Updates book with added tags using url
    [remove_book] identifier id_type: Removes book db entry and deletes book thumb
    [update_low_usr_count] min_usr_count (write_infotxt): Updates all books on which less than min_usr_count users have voted
    [add_tags] \"tag,tag,..\" url: Add tags to book
    [remove_tags] \"tag,tag,..\" url: Remove tags from book
    [read] url: Mark book as read (-> remove from li_to-read)
    [downloaded] url: Mark book as downloaded
    [show_tags] url: Display tags of book"""


def _cl_collector(args):
    pass


def _cl_export(args):
    print(args)
    mdb = MangaDB(".", args["path"])


def cli_yes_no(question_str):
    ans = input(f"{question_str} y/n:\n")
    while True:
        if ans == "n":
            return False
        elif ans == "y":
            return True
        else:
            ans = input(f"\"{ans}\" was not a valid answer, type in \"y\" or \"n\":\n")

LISTS = []
# create list with lines where one line contains 3 elements from list with corresponding
# indexes as string
# use two fstrings to first format index and value and then pad the resulting string to
# the same length
# is there a way just using one f string? -> no not without using variables, which doesnt work
# here (at least i dont think so)
DESCR = [
    " ".join([
        f"{f'[{i+n}] {LISTS[i+n]}':20}"
        for n in range(3 if (len(LISTS) - i) >= 3 else len(LISTS) - i)
    ]) for i in range(0, len(LISTS), 3)
]


# or pad index and value independently?
# DESCR = [" ".join([f"[{i+n:>2}] {LISTS[I+N]:15}" for n in range(3 if (len(LISTS)-I) >= 3 else len(LISTS)-I)]) for i in range(0, len(LISTS), 3)]
def enter_manga_lists(i):
    # only print available LISTS every fifth time
    if i % 5 == 0:
        print("\n".join(DESCR))

    while True:
        result = []
        inp = input(
            "Enter indexes (displayed in [i]) of lists the manga should be in seperated "
            "by commas:\n"
        )
        if inp:
            for ind in inp.split(","):
                try:
                    lname = LISTS[int(ind)]
                    result.append(lname)
                # (Error1, Erro2) is needed to except multiple exceptions in one except statement
                except (ValueError, IndexError):
                    logger.error(
                        "\"%s\" was not a valid list index, please re-enter list indexes",
                        ind)
                    break
            # keep looping (while) till all list names are recognized -> for doesnt break -> return
            else:
                logger.info("The following lists were selected %s", result)
                return result
        else:
            logger.info("No lists were selected!")
            # no input -> dont add to any lists
            return None
