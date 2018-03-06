#! python3
import time
import os
import sys
import re
import urllib.request
import logging

from collections import OrderedDict
from logging.handlers import RotatingFileHandler

import bs4
import pyperclip

ROOTDIR = os.path.dirname(os.path.realpath(__file__))
# CWD = os.getcwd()
dirs_root = None

logger = logging.getLogger("tsu-getter")
logger.setLevel(logging.DEBUG)

def write_to_txtf_in_root(wstring, filename):
    """
    Writes wstring to filename in dir ROOTDIR

    :param wstring: String to write to file
    :param filename: Filename
    :return: None
    """
    with open(os.path.join(ROOTDIR, filename), "w", encoding="UTF-8") as w:
        w.write(wstring)


def write_to_txtf(wstring, filename):
    """
    Writes wstring to filename

    :param wstring: String to write to file
    :param filename: Path/Filename
    :return: None
    """
    with open(filename, "w", encoding="UTF-8") as w:
        w.write(wstring)


def get_tsu_url(url):
    html = None

    # normal urllib user agent is being blocked by tsumino, send normal User-Agent in headers ;old: 'User-Agent': 'Mozilla/5.0'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'})
    try:
        site = urllib.request.urlopen(req)
    except urllib.request.HTTPError as err:
        logger.warning("HTTP Error {}: {}: \"{}\"".format(
            err.code, err.reason, url))
    else:
        html = site.read().decode('utf-8')
        site.close()
        logger.debug("Getting html done!")

    return html


def extract_info(html):
    # use OrderedDict (is a dict that remembers the order that keys were first inserted) to later just iterate over
    # list with key,val tuples also possible
    result_dict = OrderedDict()

    soup = bs4.BeautifulSoup(html, "html.parser")
    book_data = soup.select_one(
        "div.book-info-container").find_all("div", class_="book-data")

    for book_dat_div in book_data:
        tag_id = book_dat_div["id"]
        if tag_id:
            # Using a tag name as an attribute will give you only the first tag by that name -> use find_all
            if book_dat_div.a is not None:  # and book_dat_div["id"] == "Tag"
                data_list = [a.contents[0].strip()
                             for a in book_dat_div.find_all("a")]
                result_dict[tag_id] = data_list
            elif tag_id == "MyRating":
                continue
            else:
                result_dict[book_dat_div["id"]
                            ] = book_dat_div.contents[0].strip()
    logger.debug("Extracted book data!")
    return result_dict


def create_info_str(dic, url):
    lines = []
    for key, value in dic.items():
        if isinstance(value, list):
            # new f-strings, python code usable
            lines.append(f"{key}: {', '.join(value)}")
        else:
            lines.append(f"{key}: {value}")
    lines.append(f"URL: {url}")

    return "\n".join(lines)


eng_title_re = re.compile(r"^(.+) \/")
# [^abc] not a b or c
non_ascii_re = re.compile(r'[^\x00-\x7F]+')
# removed dot from forbidden windows, if python has probs with finding files that contain multiple dots do it with a separate regex
forbidden_windows_re = re.compile(r"[\<\>\:\"\/\\\|\?\*]")
# just the id is enought to be valid tsu url /Book/Info/<id>
# book_url_re = re.compile(r"^.+tsumino.com\/Book\/Info\/\d+\/.+")
book_url_re = re.compile(r"^.+tsumino.com\/Book\/Info\/\d+")


def write_inf_txt(inf_str, title, path=ROOTDIR, dirnames_in_path=dirs_root):
	eng_title = re.match(eng_title_re, title)
	# asian title after "/"
	if eng_title:
		eng_title = eng_title.group(1)
	# only eng title
	else:
		eng_title = title
	# replace consecutive non-ASCII characters with a _:
	title_sanitized = re.sub(non_ascii_re, '_', eng_title)
	# sub bad path chars
	title_sanitized = re.sub(forbidden_windows_re, '_', title_sanitized)
	# try to derive dirname from title if no dir of that name is found try the expensive search
	dirname = derive_dirname(title)
	if not os.path.isdir(os.path.join(path, dirname)):
		logger.debug(
		    "Derived dirname \"%s\" doesnt match any folder in %s: Searching for appropriate folder!", dirname, path)
		dirname = find_dir_simple(title, path, dirnames_in_path) #find_appropriate_dir(title_sanitized)
	# python ternary: a if condition else b
	# rstrip to remove trailing whitespace, -> otherweise filenotfounderror
	txt_path = os.path.join(
		dirname.rstrip(), f"[TSUMINO.COM] {title_sanitized}_info.txt") if dirname else f"[TSUMINO.COM] {title_sanitized}_info.txt"

	write_to_txtf(inf_str, os.path.join(path, txt_path))


def get_tsubook_info(url):
    html = get_tsu_url(url)
    dic = extract_info(html)
    return dic


# dirs_root initialized as None only if exec as script (name == __main__ etc) it gets set
def create_tsubook_info(url, path=ROOTDIR, dirnames_in_path=dirs_root):
    logger.debug("Starting job!")
    dic = get_tsubook_info(url)
    inf_str = create_info_str(dic, url)
    write_inf_txt(inf_str, dic["Title"], path, dirnames_in_path)
    logger.info(f"Info file written for \"{dic['Title']}\"")
    return dic


# always two spaces between eng and asian title when using tsu zip
tsu_eng_zip_re = re.compile(r"^(.+)\s{2,}")


def find_dir_simple(title, path=ROOTDIR, dirnames_in_path=dirs_root):
    dir_eng = re.match(eng_title_re, title)
    # dir_eng will be None if alrdy only english title
    dir_eng = dir_eng.group(1) if dir_eng else title

    # possiblity to pass dirnames so we dont have to find them every func call
    if dirnames_in_path is None:
        dirnames_in_path = [e for e in os.listdir(path) if os.path.isdir(os.path.join(path, e))]

    matching_dirs = [dirname for dirname in dirnames_in_path if re.sub(forbidden_windows_re, '', 
                     dir_eng) in dirname]
    if len(matching_dirs) > 1:
        logger.warning("More than one matching dir found, taking the first one: %s", matching_dirs)

    # dir might not exist yet return None if no matching dirs
    return matching_dirs[0] if matching_dirs else None


def find_appropriate_dir(title_sanitized, path=ROOTDIR, dirnames_in_path=dirs_root):
    # refresh dirs every time we want to write a txt or only at startup or at set intervals?
    # print("title: ", f"\"{title_sanitized}\"")
    # build regex pattern, sub {} with title(sanitized)
    # IMPORTANT use re.escape to escape special chars in title_sanitized (not sanitized for regex)
    d_name_re = r"(\[TSUMINO.COM\])?\s?\s?{}$".format(
        re.escape(title_sanitized))

    if dirnames_in_path is None:
        dirnames_in_path = [e for e in os.listdir(path) if os.path.isdir(os.path.join(path, e))]

    found_dir = None
    for dirname in dirnames_in_path:
        # normpath -> strip trailing "/", basepath gives last part of path
        dirname = os.path.basename(os.path.normpath(dirname))
        dir_eng = re.match(tsu_eng_zip_re, dirname)
        if dir_eng:
            # trailing spaces alrdy removes with re
            dir_eng = dir_eng.group(1)
        else:
            # alrdy was only eng title, remove space from end of str
            # so regex d_name_re works correctly
            dir_eng = dirname.rstrip()
        # print("dirname: ", f"\"{dirname}\"", "\n", "dir_eng: ", f"\"{dir_eng}\"")
        # sanitize dirname, since title is also sanitized
        dir_eng = re.sub(non_ascii_re, '_', dir_eng)
        # print("saniz dir_eng: ", f"\"{dir_eng}\"")
        # re.search instead of match since match only matches at beginning of str (same as using ^ in regex)
        if re.search(d_name_re, dir_eng):
            found_dir = dirname
            break
    logger.debug("Found dir: {}".format(found_dir))
    return found_dir


titles_re = re.compile(r"^(.+) \/ (.+)$")


def derive_dirname(title):
    # not needed since replacing forbidden chars does the same
    # titles = re.match(titles_re, title)
    dirname = None
    # if titles:
    # 	# tsumino zip name is "[TSUMINO.COM] {eng name}  {asian name}" -> 2 spaces between eng and asian name
    # 	dirname = f"[TSUMINO.COM] {titles.group(1)}  {titles.group(2)}"
    # else:
    # 	# alrdy was only eng title
    # 	dirname = f"[TSUMINO.COM] {title}"
    # forbidden path chars get replaced (in name of zip) by empty str (leaving 2 spaces from b4)
    dirname = re.sub(forbidden_windows_re, '', title)
    dirname = f"[TSUMINO.COM] {dirname}"
    # It is not true for logger statement because it relies on former "%" format like string to provide lazy interpolation
    # of this string using extra arguments given to the logger call. For instance instead of doing:
    # logger.error('oops caused by %s' % exc)
    # you should do
    # logger.error('oops caused by %s', exc)
    # so the string will only be interpolated if the message is actually emitted.
    # You can't benefit of this functionality when using .format().
    # Per the Optimization section of the logging docs:
    # Formatting of message arguments is deferred until it cannot be avoided. However, computing the arguments passed to
    # the logging method can also be expensive, and you may want to avoid doing it if the logger will just throw away your event.
    logger.debug("Derived dirname: %s", dirname)
    return dirname


def is_tsu_book_url(url):
    if re.match(book_url_re, url):
        return True
    else:
        return False


class ClipboardWatcher:
	"""Watches for changes in clipboard that fullfill predicate and get sent to callback

	I create a subclass of threading.Thread, override the methods run and __init__ and create an instance of this class.
	By calling watcher.start() (not run()!), you start the thread.
	To safely stop the thread, I wait for -c (Keyboard-interrupt) and tell the thread to stop itself.
	In the initialization of the class, you also have a parameter pause to control how long to wait between tries.
	by Thorsten Kranz"""
	# predicate ist bedingung ob gesuchter clip content
	# hier beim aufruf in main funktion is_url_but_not_sgasm

	def __init__(self, predicate, callback, pause=5.):
		self._predicate = predicate
		if callback is None:
			self._callback = self.add_found
		else:
			self._callback = callback
		self._found = []
		self._pause = pause
		self._stopping = False

	def run(self):
		recent_value = ""
		while not self._stopping:
			tmp_value = pyperclip.paste()
			if tmp_value != recent_value:
				recent_value = tmp_value
				# if predicate is met
				if self._predicate(recent_value):
					# call callback
					self._callback(recent_value)
			time.sleep(self._pause)

	def add_found(self, item):
		logger.info("Found item: %s", item)
		self._found.append(item)

	def get_found(self):
		return self._found

	def stop(self):
		self._stopping = True


def watch_clip():
    # predicate = is_tsu_book_url, callback = create_tsubook_info
    watcher = ClipboardWatcher(is_tsu_book_url, create_tsubook_info, 0.1)
    try:
        logger.info("Watching clipboard...")
        watcher.run()
    except KeyboardInterrupt:
        watcher.stop()
        logger.info("Stopped watching clipboard!")


def watch_clip_dl_after():
	found = None
	# predicate = is_tsu_book_url, callback = create_tsubook_info
	watcher = ClipboardWatcher(is_tsu_book_url, None, 0.1)
	try:
		logger.info("Watching clipboard...")
		watcher.run()
	except KeyboardInterrupt:
		found = watcher.get_found()
		watcher.stop()
		logger.info("Stopped watching clipboard!")
	return found


txt_title_re = re.compile(r"Title: (.+)")

def get_book_title_txt(txtpath):
	conts = None
	with open(txtpath, mode='r', encoding="UTF-8") as f:
		conts = f.read()
	conts = re.search(txt_title_re, conts)
	if conts:
		return conts.group(1)
	else:
		return None


def move_txt_to_appropriate_folder(txtpath, title, path=ROOTDIR, dirnames_in_path=dirs_root):
    txtname = os.path.basename(os.path.normpath(txtpath))
    # try to derive dirname from title if no dir of that name is found try the expensive search
    dirname = derive_dirname(title)
    if not os.path.isdir(os.path.join(path, dirname)):
        logger.debug("Derived dirname doesnt match any folder in ROOTDIR: Searching for appropriate folder!")
        # almost does the same thing but find_dir_simple much simpler (may have partial match when titles are extremely alike, which mb wouldnt happen with find_appropriate_dir)
        # dirname = find_appropriate_dir(txtname, path, dirnames_in_path)
        dirname = find_dir_simple(title, path, dirnames_in_path)
    if dirname:
        # rstrip to remove trailing whitespace, -> otherweise filenotfounderror
        new_txt_path = os.path.join(path, dirname.rstrip(), txtname)

        # os.rename won't handle files across different devices. Use shutil.move
        os.rename(txtpath, new_txt_path)
        logger.info("Succesfully moved %s into its appropriate folder", txtname)
    else:
        logger.warning("Couldnt find appropriate folder for \"%s\"", title)


def list_infotxt_folder(dpath):
	result = [e for e in os.listdir(dpath) if e.endswith("info.txt")]
	return result


def move_txts_to_folders(dpath):
    l = list_infotxt_folder(dpath)
    for txt in l:
        title = get_book_title_txt(os.path.join(dpath, txt))
        if not title:
            logger.warning("Title couldnt be extracted from %s", txt)
            continue
        move_txt_to_appropriate_folder(os.path.join(dpath, txt), title, dpath)


def check_subdirs_txt(dpath):
    dirl = [e for e in os.listdir(dpath) if os.path.isdir(os.path.join(dpath, e))]
    missing = []
    for d in dirl:
        # check every folder or only ones that contain images (jpg/png)?
        # any file ending with info.txt, CAREFUL folders with that ending also count
        # txtpresent = any((f.endswith("info.txt") for f in os.listdir(os.path.join(dpath, d))))
        txtpresent = [f for f in os.listdir(
            os.path.join(dpath, d)) if f.endswith("info.txt")]
        if not txtpresent:
            missing.append(d)
        elif len(txtpresent) > 1:
            logger.warning(
                "More than one info.txt in folder \"%s\": %s", d, txtpresent)
    return missing


def test_derive_dirname():
	titles = [("ASS Horufo-kun 2 / ASS掘るフォくん2", "[TSUMINO.COM] ASS Horufo-kun 2  ASS掘るフォくん2"),
				("Mama Para ~Chijo Zukan~ / ママパラ～痴女図鑑～" , "[TSUMINO.COM]  Mama Para ~Chijo Zukan~  ママパラ～痴女図鑑～"),
				("Ojou-sama to Maid no Midara na Seikatsu / お嬢様とメイドのみだらな性活 + とらのあなリーフレット", "[TSUMINO.COM] Ojou-sama to Maid no Midara na Seikatsu  お嬢様とメイドのみだらな性活 + とらのあなリーフレット"),
				("ToraManga Plus", "[TSUMINO.COM] ToraManga Plus"),
				("NEET (FAKKU)", "[TSUMINO.COM] NEET (FAKKU)"),
				("PANDRA -Shiroki Yokubou Kuro No Kibou- II / PANDRA―白き欲望 黒の希望―II", "[TSUMINO.COM] PANDRA -Shiroki Yokubou Kuro No Kibou- II  PANDRA―白き欲望 黒の希望―II"),
				("PANDRA -Shiroki Yokubou Kuro no Kibou- / PANDRA―白き欲望 黒の希望―", "[TSUMINO.COM] PANDRA -Shiroki Yokubou Kuro no Kibou-  PANDRA―白き欲望 黒の希望―"),
				("Producer tte, Hee~ Gal Mono Bakkari Mottenda / プロデューサーって、へえ～♪ギャルモノばっかり持ってんだ♥", "[Sian] Producer tte, Hee~ Gal Mono Bakkari Mottenda")]
	for t, d in titles:
		write_inf_txt("test", t)
		# dname = derive_dirname(t)
		# match = dname == d
		# print(match)
		# if not match:
		# 	print(f"derived: \"{dname}\"\ndirname: \"{d}\"\n")


if __name__ == "__main__":

    handler = RotatingFileHandler(os.path.join(ROOTDIR, "tsuinfo.log"),
                                  maxBytes=1048576, backupCount=5, encoding="UTF-8")
    handler.setLevel(logging.DEBUG)

    # create a logging format
    formatter = logging.Formatter(
        "%(asctime)-15s - %(name)-9s - %(levelname)-6s - %(message)s")
    # '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    handler.setFormatter(formatter)

    # add the handlers to the logger
    logger.addHandler(handler)

    # create streamhandler
    stdohandler = logging.StreamHandler(sys.stdout)
    stdohandler.setLevel(logging.INFO)

    # create a logging format
    formatterstdo = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", "%H:%M:%S")
    stdohandler.setFormatter(formatterstdo)
    logger.addHandler(stdohandler)

    # variables declared here have same scope as module level stuff declared at top
    # -> set dirs_root here so its not None when tsu_info_getter is used as script
    # only returns dirnames not whole path
    # was viable as a script that just gets dropped and executed in the cur dir
    dirs_root = [e for e in os.listdir(ROOTDIR) if os.path.isdir(e)]

    optnr = input("OPTIONS: [1] Watch clipboard and get info directly [2] Move txts into folders "
                              "[3] Check if every manga folder contains info.txt [4] Watch clipboard and get info afterwards [5] Get tsu info for urls in \"tsuurls.txt\"\n")
    if optnr == "1":
            watch_clip()
    elif optnr == "2":
            move_txts_to_folders(ROOTDIR)
    elif optnr == "3":
            logger.info("Folders that are missing info files:\n%s", "\n".join(check_subdirs_txt(ROOTDIR)))
    elif optnr == "4":
            l = watch_clip_dl_after()
            logger.info("Started working on list with %i items", len(l))
            try:
                    while l:
                            item = l.pop(0)
                            create_tsubook_info(item, ROOTDIR, dirs_root)
                            time.sleep(0.3)
            except Exception:
                    # item is alrdy removed even though it failed on it
                    logger.error("Job was interrupted, the following entries were not processed:\n%s\n%s", item, "\n".join(l))
                    raise
    elif optnr == "5":
        with open("tsuurls.txt", "r", encoding="UTF-8") as f:
            l = f.read().strip().splitlines()
        try:
                while l:
                        item = l.pop(0)
                        create_tsubook_info(item, ROOTDIR, dirs_root)
                        time.sleep(0.3)
        except Exception:
                # item is alrdy removed even though it failed on it
                logger.error("Job was interrupted, the following entries were not processed:\n%s\n%s", item, "\n".join(l))
                raise
    elif optnr == "6":
        test_derive_dirname()


# C-struct-like structure in python using dictionaries(wont return error when setting on wrong key), namedtuple(but its immutable, as in you cant to this Player(x=10,y=0) Player.x += 1 or a class
# class Bunch:
# ...     def __init__(self, **kwds):
# ...         self.__dict__.update(kwds)
# ...
# >>> mystruct = Bunch(field1=value1, field2=value2)
# or using __slots__ for less memory overhead and faster attribute access
# (must inherit from object, and all inherting classes must declare __slots__ and cant have __dict__ entry)
# class AB(object):
#     __slots__ = ('a', 'b')
# test = AB(); test.a = 1
# but then test = AB(0,1) isnt possible NO it is possible if you define an __init__ function
# >>> class AB(object):
# ...     __slots__ = ("a", "b")
# ...     def __init__(self, a, b):
# ...             self.a = a
# ...             self.b = b
# ...
# >>> test1 = AB(5,9)
# >>> test1.a
# 5
