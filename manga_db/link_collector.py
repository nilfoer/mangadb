import logging
import time
import cmd
import re
import json
import os

import pyperclip

from . import extractor
from .threads import import_multiple

logger = logging.getLogger(__name__)


class LinkCollector(cmd.Cmd):
    # start with LinkCollector.cmdloop()
    intro = "Welcome to MangaDB's LinkCollector. Type help or ? to show commands.\n"
    prompt = '(lc) '

    URL_RE = re.compile(r"(?:https?://)?(?:\w+\.)?(\w+\.\w+)/")

    def __init__(self, data_path, standard_lists):
        super().__init__()
        self.data_root = os.path.realpath(os.path.normpath(data_path))
        # must be immutable
        self._standard_downloaded = "downloaded" in standard_lists
        self._standard_lists = tuple((x for x in standard_lists if x != "downloaded"))
        self.links = {}
        self._recent_value = ""

    def watch_clip(self):
        logger.info("Watching clipboard...")
        # prob doesnt matter but local var access is faster since it doesnt have to
        # look up the var in the __dict__ of local var self
        recent_value = self._recent_value
        try:
            while True:
                tmp_value = pyperclip.paste()
                if tmp_value != recent_value:
                    recent_value = tmp_value
                    yield recent_value
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Stopped watching clipboard!")
            return None

    def do_collect(self, args):
        for url in self.watch_clip():
            # dont overwrite (possibly modified by set_lists) entry in self.links
            if url is not None and url not in self.links:
                try:
                    extractor.find(url)
                    logger.info("Found supported url: %s", url)
                    self.links[url] = {"lists": self._standard_lists,
                                       "downloaded": self._standard_downloaded}
                    self._recent_value = url
                except extractor.NoExtractorFound:
                    logger.info("Unsupported URL!")

    def do_add(self, args):
        arg_li = args.split()
        if not arg_li:
            print("No arguments supplied!")
            return
        url, lists = arg_li[0], arg_li[1:]
        downloaded = "downloaded" in lists
        if downloaded:
            lists.remove("downloaded")
        try:
            extractor.find(url)
            logger.info("Added url: %s(%s, %s)", url, lists, downloaded)
            self.links[url] = {"lists": lists, "downloaded": downloaded}
            self._recent_value = url
        except extractor.NoExtractorFound:
            logger.info("Unsupported URL!")

    def do_print(self, url):
        if url == "all":
            print("\n".join((f"{k}: {v}" for k, v in self.links.items())))
        elif url:
            try:
                print(self.links[url])
            except KeyError:
                print("No such url: {url}")
        else:
            if self._recent_value:
                try:
                    print(self.links[self._recent_value])
                except KeyError:
                    print("Recent value was deleted from links!")
            else:
                print("No links yet!")

    def do_p(self, url):
        """Alias for print"""
        self.do_print(url)

    def do_set_standard_lists(self, args):
        """
        Sets standard lists that get added to book when collecting links
        Usage: set_standard_lists [list [list ...]]
        use 'recent' as url to change lists of most recently added url
        """
        lists = args.split()
        if not lists:
            print("No arguments supplied!")
            return
        self._standard_downloaded = "downloaded" in lists
        if self._standard_downloaded:
            lists.remove("downloaded")
        self._standard_lists = tuple(lists)
        logger.info("Changed standard lists to %s", lists)

    def do_set_lists(self, args):
        """
        Sets lists of book at url to provided lists
        Usage: set_lists url [list [list ...]]
        use 'recent' as url to change lists of most recently added url
        """
        arg_li = args.split()
        if not arg_li:
            print("No arguments supplied!")
            return
        # shortcut to change most recent book
        url = arg_li[0] if arg_li[0] not in ("recent", "r") else self._recent_value
        if not url:
            print("No links yet!")
            return
        lists = arg_li[1:]
        if url in self.links:
            downloaded = "downloaded" in lists
            if downloaded:
                lists.remove("downloaded")
            self.links[url]["lists"] = lists
            self.links[url]["downloaded"] = downloaded
            logger.info("Changed lists of %s to %s", url, lists)
        else:
            print("Given url wasnt found in links!")

    def do_sl(self, args):
        """Alias for set_lists"""
        self.do_set_lists(args)

    def do_not_downloaded(self, url):
        if not url:
            print("URL needed!")
            return
        url = url if url not in ("recent", "r") else self._recent_value
        if not url:
            print("No links yet!")
            return
        try:
            self.links[url]["downloaded"] = False
        except KeyError:
            print("No such url!")

    def do_ndl(self, url):
        self.do_not_downloaded(url)

    def do_remove(self, url):
        """
        Remove url from links: remove url
        Shortcut: remove recent - to remove last url"""
        if not url:
            print("No arguments supplied!")
            return
        url = url if url not in ("recent", "r") else self._recent_value
        if not url:
            print("No links to remove!")
            return
        rem = self.links.pop(url, None)
        if rem is not None:
            logger.info("Removed %s: %s from link list!", url, rem)

    def do_import(self, args):
        logger.info("Started working on list with %d items!", len(self.links))
        try:
            import_multiple(self.data_root, self.links)
        # baseexception so we also except KeyboardInterrupt etc.
        except BaseException:
            self.export_json("link_collect_resume.json")
            logger.error("Unexepected crash! Saved links to link_collect_resume.json!"
                         " Resume working on list with option collect --resume")
            raise
        self.links = {}
        self._recent_value = ""
        logger.info("Finished working on list!")

    def do_exit(self, args):
        if self.links:
            imp = cli_yes_no("Do you want to import the collected links before exiting?\n"
                             "They're gonna be lost otherwise!")
            if imp:
                self.do_import(None)
        # cmdloop returns when postcmd() method returns true value
        return True

    def do_export(self, args):
        self.export_json("link_collect_resume.json")

    def export_json(self, filename):
        with open(filename, "w", encoding="UTF-8") as f:
            f.write(json.dumps(self.links))

    @classmethod
    def from_json(cls, filename, data_path, standard_lists):
        lc = cls(data_path, standard_lists)
        if not os.path.isfile(filename):
            logger.warning("Couldn't resume from file 'link_collector_resume.json' it wasn't found"
                           " in the current working directory")
        else:
            with open(filename, "r", encoding="UTF-8") as f:
                links = json.loads(f.read())
            lc.links = links
        return lc


def cli_yes_no(question_str):
    ans = input(f"{question_str} y/n:\n")
    while True:
        if ans == "n":
            return False
        elif ans == "y":
            return True
        else:
            ans = input(f"\"{ans}\" was not a valid answer, type in \"y\" or \"n\":\n")


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
