import sys
import argparse
import os.path
import logging

from .webGUI import create_app
from .manga_db import MangaDB
from .db.export import export_csv_from_sql
from .link_collector import LinkCollector

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Command-line interface for MangaDB - A "
                                     "database to keep track of your manga reading habits!")

    parser.add_argument("-db", "--db-path", default="./instance/manga_db.sqlite", type=str,
                        help="Path to db file; Default uses file named 'manga_db.sqlite' "
                             "in directory instance")
    subparsers = parser.add_subparsers(title='subcommands', description='valid subcommands',
                                       help='sub-command help', dest="subcmd")

    webgui = subparsers.add_parser("webgui", aliases=["web"])
    webgui.set_defaults(func=_cl_webgui)

    collector = subparsers.add_parser("link_collector", aliases=["collect"])
    collector.add_argument("-sl", "--standard-list", help="Standard list that gets added to all "
                           "links collected!", nargs="*", default=())
    collector.add_argument("-re", "--resume", action="store_true", help="Resume importing books "
                           "from resume file")
    collector.add_argument("-dp", "--data-path", default="./instance/", type=str,
                           help="Path to folder containing manga_db.sqlite file; Default uses"
                                "instance folder current working directory")
    collector.set_defaults(func=_cl_collector)

    get_info = subparsers.add_parser("get_info")
    get_info.add_argument("url", type=str, help="URL to book on supported site")
    get_info.add_argument("-o", "--output-filename", type=str,
                          help="Relative or absolute path to output file")
    get_info.set_defaults(func=_cl_get_info)

    import_book = subparsers.add_parser("import_book")
    import_book.add_argument("url", type=str, help="URL to book on supported site")
    import_book.add_argument("list", nargs="*", help="List the book should be added to",
                             type=str)
    import_book.set_defaults(func=_cl_import_book)

    show_book = subparsers.add_parser("show_book")
    show_book.add_argument("id", type=int, help="Book ID in database")
    show_book.set_defaults(func=_cl_show_book)

    export = subparsers.add_parser("export", aliases=["exp"])
    export.add_argument("path", type=str, help="Path/Filename of csv file the db should be "
                        "exported to")
    export.set_defaults(func=_cl_export)

    args = parser.parse_args()
    if len(sys.argv) == 1:
        # default to stdout, but stderr would be better (use sys.stderr, then exit(1))
        parser.print_help()
        sys.exit(0)
    # let webgui handle db_con when subcmd is selected
    if args.subcmd == "webgui":
        args.func()
    else:
        db_path = os.path.realpath(os.path.normpath(args.db_path))
        mdb = MangaDB(os.path.dirname(db_path), db_path)
        args.func(args, mdb)


def _cl_import_book(args, mdb):
    bid, book, _ = mdb.import_book(args.url, args.list)


def _cl_get_info(args, mdb):
    book, _, _ = MangaDB.retrieve_book_data(args.url)
    if book is None:
        return
    if args.output_filename:
        exp_str = book.to_export_string()
        with open(args.output_filename, "w", encoding="UTF-8") as w:
            w.write(exp_str)
        print(exp_str)
        logger.info("Info of '%s' saved in file '%s'", args.url, args.output_filename)
    else:
        print(book.to_export_string())


def _cl_show_book(args, mdb):
    b = mdb.get_book(args.id)
    if b:
        print(b.to_export_string())
    else:
        print("No book with that id!")


def _cl_collector(args, mdb):
    if args.resume:
        lc = LinkCollector.from_json("link_collect_resume.json", args.data_path,
                                     args.standard_list)
    else:
        lc = LinkCollector(args.data_path, args.standard_list)
    lc.cmdloop()


def _cl_export(args, mdb):
    export_csv_from_sql(args.path, mdb.db_con)
    logger.info(f"Exported database at {os.path.abspath(args.db_path)} to "
                f"{os.path.abspath(args.path)}!")


def _cl_webgui():
    # use terminal environment vars to set debug etc.
    # windows: set FLASK_ENV=development -> enables debug or set FLASK_DEBUG=1
    app = create_app()
    # use threaded=False so we can leverage MangaDB's id_map
    # also makes sense since we only want to support one user (at least with write access)
    app.run(threaded=False, port=7578)


def cli_yes_no(question_str):
    ans = input(f"{question_str} y/n:\n")
    while True:
        if ans == "n":
            return False
        elif ans == "y":
            return True
        else:
            ans = input(f"\"{ans}\" was not a valid answer, type in \"y\" or \"n\":\n")
