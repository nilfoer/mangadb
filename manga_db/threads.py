import os
import time
import logging
from threading import Thread, current_thread
from queue import Queue

from typing import TYPE_CHECKING, Tuple, Union, Optional

from .manga_db import MangaDB
from .manga import Book
from .ext_info import ExternalInfo
from .extractor.base import MangaExtractorData

if TYPE_CHECKING:
    from .link_collector import UrlList, ImportData

logger = logging.getLogger(__name__)

NUMBER_OF_THREADS = 3
URL_WORKER_SLEEP = 1
RETRIEVE_BOOK_DATA, DOWNLOAD_COVER = 0, 1


def thread_retrieve_data_or_cover(url_queue: Queue, book_queue: Queue) -> None:
    while True:
        # will block on the statement .get() until the queue has something to return, so it
        # is safe to start the threads before there is anything in the queue
        task, data = url_queue.get()
        if task is None:
            break
        if task == RETRIEVE_BOOK_DATA:
            try:
                url = data
                print(f"{current_thread().name}: Getting data for url {url}")
                extr_data, thumb_url_opt, _ = MangaDB.retrieve_book_data(url)
                # also put None in the queue so importer know the link was processed
                book_queue.put((url, extr_data, thumb_url_opt))
            except Exception:
                # communicate to importer that failed link was processed
                # so importer can terminate properly
                book_queue.put((None, None, None))
                raise
            finally:
                # wrap task_done in finally so even when we get an exception (thread wont exit)
                # the task will be marked as done
                # otherwise there could be mixups

                # Indicate that a formerly enqueued task is complete.
                # Used by queue consumer threads.
                # For each get() used to fetch a task, a subsequent call to task_done()
                # tells the queue that the processing on the task is complete.
                url_queue.task_done()
        elif task == DOWNLOAD_COVER:
            try:
                book_id: int
                # 'thumb_url: str' was defined from ln34 in other if branch
                # since a function is one scope -> need to rename
                thumb_url: str
                cover_dir_path: str
                book_id, thumb_url, cover_dir_path = data
                print(f"{current_thread().name}: Downloading cover from {thumb_url}")
                MangaDB.download_cover(thumb_url, cover_dir_path, book_id)
            finally:
                url_queue.task_done()
        else:
            print("Didnt recognize task {task}!")
        time.sleep(URL_WORKER_SLEEP)


def single_thread_import(data_path: str, url_lists: 'UrlList', to_process: int,
                         url_queue: Queue, book_queue: Queue) -> None:
    # only the thread that created the sqlite conn can use it!!
    mdb = MangaDB(data_path, os.path.join(data_path, "manga_db.sqlite"))

    processed = 0
    while True:
        # check on top so it doesnt get skipped if we continue
        if processed == to_process:
            # send url workers signal to stop
            for _ in range(NUMBER_OF_THREADS):
                url_queue.put((None, None))
            break
        time.sleep(0.1)

        try:
            url, extr_data, thumb_url = book_queue.get()
            if extr_data is None:
                continue
            print(f"{current_thread().name}: Adding book at {url}")

            book, ext_info = mdb.book_and_ei_from_data(extr_data)
            book.list = url_lists[url]["lists"]
            ext_info.downloaded = 1 if url_lists[url]["downloaded"] else 0

            bid, outdated_on_ei_id = book.save(block_update=True)
        except Exception:
            # except needed for else
            raise
        else:
            if bid is None:
                logger.info("Book at url '%s' was already in DB!",
                            url if url is not None else book.ext_infos[0].url)
                # load book thats already in db and try to add ext_info to it
                # if its not already on the book
                b = mdb.get_book(title_eng=book.title_eng, title_foreign=book.title_foreign)
                if not any(ei for ei in b.ext_infos if ei.id_onpage == ext_info.id_onpage
                           and ei.imported_from == ext_info.imported_from):
                    ext_info.book = b
                    ext_info.book_id = b.id
                    b.ext_infos.append(ext_info)
                    ext_info.save()
                    logger.info("Added external info at url '%s' to book instead!",
                                url if url is not None else book.ext_infos[0].url)
                # also counts as processed/done
                # book_done called in finally
            else:
                cover_dir_path = os.path.join(mdb.root_dir, "thumbs")
                url_queue.put((DOWNLOAD_COVER, (book.id, thumb_url, cover_dir_path)))
        finally:
            processed += 1
            # wrap task_done in finally so even when we get an exception (thread wont exit)
            # the task will be marked as done
            # otherwise there could be mixups esp. with the covers and their filenames
            book_queue.task_done()


def import_multiple(data_path: str, url_lists: 'UrlList') -> None:
    data_path = os.path.realpath(data_path)
    # make sure db file and thumbs folder exists
    if not os.path.isfile(os.path.join(data_path, "manga_db.sqlite")):
        logger.error("Couldn't find manga_db.sqlite in %s", data_path)
        return
    os.makedirs(os.path.join(data_path, "thumbs"), exist_ok=True)

    # type annotation not possible without putting it in str
    # errors with type obj not subscriptable
    url_queue: "Queue[Tuple[Optional[int], Optional[Union[str, Tuple[int, str, str]]]]]" = Queue()
    book_queue: "Queue[Tuple[Optional[str], Optional[MangaExtractorData], Optional[str]]]" = Queue()
    print("** Filling URL Queue! **")
    for url, url_data in url_lists.items():
        url_queue.put((RETRIEVE_BOOK_DATA, url))

    print("** Starting threads! **")
    url_workers = []
    for i in range(NUMBER_OF_THREADS):
        t = Thread(
                name=f"URL-Worker {i}", target=thread_retrieve_data_or_cover,
                args=(url_queue, book_queue)
                )
        url_workers.append(t)
        t.start()

    # importer thread counts process urls/books and stops
    to_process = len(url_lists)
    # only one thread writes to db
    importer = Thread(
            name="Importer", target=single_thread_import,
            # program may exit if there are only daemon threads left
            args=(data_path, url_lists, to_process, url_queue, book_queue)
            )
    importer.start()

    print("** Waiting for threads to finish! **")

    for t in url_workers:
        print(f"** Waiting on thread {t.name} **")
        t.join()

    print("** Done! **")
