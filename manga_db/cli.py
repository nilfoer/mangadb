import sys
import argparse
import os.path
import logging

from typing import Optional

from .webGUI import create_app
from .manga_db import MangaDB, update_cookies_from_file
from .db.export import export_csv_from_sql
from .link_collector import LinkCollector

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Command-line interface for MangaDB - A "
                                     "database to keep track of your manga reading habits!")

    parser.add_argument("-p", "--path", default=None, type=str,
                        help="Path to directory where user files will be stored "
                             "inside of! MangaDB will be looking for a file named "
                             "'manga_db.sqlite' inside that folder!")
    parser.add_argument("--cookies", type=str,
                        help="Cookies that might be needed to access protected websites by "
                             "services like cloudflare will be read from this path upon start. "
                             "The User-Agent should be included in the cookies file as a "
                             "comment of the form: '# User-Agent: Mozilla/5.0...'")
    subparsers = parser.add_subparsers(title='subcommands', description='valid subcommands',
                                       help='sub-command help', dest="subcmd")

    webgui = subparsers.add_parser("webgui", aliases=["web"])
    webgui.add_argument("-o", "--open", action="store_true",
                        help="Run on you machine's IP and make the webGUI accessible from your LAN")
    webgui.add_argument("-po", "--port", type=int, default=7578,
                        help="Port that the webGUI server should use")
    webgui.set_defaults(func=_cl_webgui)

    collector = subparsers.add_parser("link_collector", aliases=["collect"])
    collector.add_argument("-sl", "--standard-list", help="Standard list that gets added to all "
                           "links collected!", nargs="*", default=())
    collector.add_argument("-re", "--resume", action="store_true", help="Resume importing books "
                           "from resume file")
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
    export.add_argument("csv_path", type=str, help="Path/Filename of csv file the db should be "
                        "exported to")
    export.set_defaults(func=_cl_export)

    args: argparse.Namespace = parser.parse_args()
    if len(sys.argv) == 1:
        # default to stdout, but stderr would be better (use sys.stderr, then exit(1))
        parser.print_help()
        sys.exit(0)

    mdb_path = os.path.abspath(os.path.normpath(args.path)) if args.path else None
    # let webgui handle db_con when subcmd is selected
    if args.func is _cl_webgui:  # use function for comparison to account for aliases
        # flask instance_path must be absolute!
        args.func(args, instance_path=mdb_path)
    else:
        # even when called from e.g. a batch file argv[0] is still:
        # argv0: D:\SYNC\coding\tsu-info\run_manga_db.py
        mdb_path = mdb_path if mdb_path else os.path.join(os.path.dirname(sys.argv[0]), "instance")
        os.makedirs(mdb_path, exist_ok=True)
        mdb = MangaDB(mdb_path, os.path.join(mdb_path, "manga_db.sqlite"))

        # load cookies file
        if args.cookies:
            update_cookies_from_file(args.cookies)
        args.func(args, mdb)


def _cl_import_book(args: argparse.Namespace, mdb: MangaDB) -> None:
    bid, book, _ = mdb.import_book(args.url, args.list)


def _cl_get_info(args: argparse.Namespace, mdb: MangaDB) -> None:
    extr_data, _, _ = MangaDB.retrieve_book_data(args.url)
    if extr_data is None:
        return

    book = mdb.book_from_data(extr_data)
    if args.output_filename:
        exp_str = book.to_export_string()
        with open(args.output_filename, "w", encoding="UTF-8") as w:
            w.write(exp_str)
        print(exp_str)
        logger.info("Info of '%s' saved in file '%s'", args.url, args.output_filename)
    else:
        print(book.to_export_string())


def _cl_show_book(args: argparse.Namespace, mdb: MangaDB) -> None:
    b = mdb.get_book(args.id)
    if b:
        print(b.to_export_string())
    else:
        print("No book with that id!")


def _cl_collector(args: argparse.Namespace, mdb: MangaDB) -> None:
    if args.resume:
        lc = LinkCollector.from_json("link_collect_resume.json", mdb.root_dir,
                                     args.standard_list)
    else:
        lc = LinkCollector(mdb.root_dir, args.standard_list)
    lc.cmdloop()


def _cl_export(args: argparse.Namespace, mdb: MangaDB) -> None:
    export_csv_from_sql(args.csv_path, mdb.db_con)
    logger.info(f"Exported database at {os.path.join(mdb.root_dir, 'manga_db.sqlite')} to "
                f"{os.path.abspath(args.csv_path)}!")


def _cl_webgui(args: argparse.Namespace, instance_path: Optional[str] = None) -> None:
    # use terminal environment vars to set debug etc.
    # windows: set FLASK_ENV=development -> enables debug or set FLASK_DEBUG=1
    app = create_app(instance_path=instance_path)
    # use threaded=False so we can leverage MangaDB's id_map
    # also makes sense since we only want to support one user (at least with write access)
    # use host='0.0.0.0' or ip to run on machine's ip address and be accessible over lan
    if args.open:
        app.run(threaded=False, host='0.0.0.0', port=args.port)
    else:
        app.run(threaded=False, port=args.port)


def cli_yes_no(question_str: str) -> bool:
    ans = input(f"{question_str} y/n:\n")
    while True:
        if ans == "n":
            return False
        elif ans == "y":
            return True
        else:
            ans = input(f"\"{ans}\" was not a valid answer, type in \"y\" or \"n\":\n")
