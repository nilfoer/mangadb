import logging
import time
import cmd
import re

import pyperclip

from . import extractor

logger = logging.getLogger(__name__)


class LinkCollector(cmd.Cmd):
    # start with LinkCollector.cmdloop()
    intro = "Welcome to MangaDB's LinkCollector. Type help or ? to show commands.\n"
    prompt = '(lc) '

    URL_RE = re.compile(r"(?:https?://)?(?:\w+\.)?(\w+\.\w+)/")

    def __init__(self, standard_lists):
        super().__init__()
        # must be immutable
        self._standard_lists = tuple(standard_lists)
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
                    self.links[url] = self._standard_lists
                    self._recent_value = url
                except extractor.NoExtractorFound:
                    logger.info("Unsupported URL!")

    def do_set_lists(self, args):
        """
        Sets lists of book at url to provided lists
        Usage: set_lists url [list [list ...]]
        use 'recent' as url to change lists of most recently added url
        """
        arg_li = args.split()
        # shortcut to change most recent book
        url = arg_li[0] if arg_li[0] != "recent" else self._recent_value
        lists = arg_li[1:]
        if url in self.links:
            self.links[url] = tuple(lists)
        else:
            print("Given url wasnt found in links!")

    def do_remove(self, url):
        """
        Remove url from links: remove url
        Shortcut: remove recent - to remove last url"""
        rem = self.links.pop(url if url != "recent" else self._recent_value, None)
        if rem is not None:
            logger.info("Removed %s from link list!", rem)

    def do_exit(self, args):
        # cmdloop returns when postcmd() method returns true value
        return True


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
