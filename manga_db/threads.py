import os
import logging
from threading import Thread
from queue import Queue

from .manga_db import MangaDB
from .manga import Book
from .ext_info import ExternalInfo

logger = logging.getLogger(__name__)

NUMBER_OF_THREADS = 3
RETRIEVE_BOOK_DATA, DOWNLOAD_COVER = 0, 1


def thread_retrieve_data_or_cover(url_queue, book_queue):
    while True:
        # will block on the statement .get() until the queue has something to return, so it
        # is safe to start the threads before there is anything in the queue
        task, data = url_queue.get()
        if task is None:
            break
        if task == RETRIEVE_BOOK_DATA:
            url, lists = data
            print(f"Getting data for url {url}")
            extr_data, thumb_url = MangaDB.retrieve_book_data(url)
            if extr_data is not None:
                book_queue.put((url, extr_data, thumb_url))
            # Indicate that a formerly enqueued task is complete.
            # Used by queue consumer threads.
            # For each get() used to fetch a task, a subsequent call to task_done()
            # tells the queue that the processing on the task is complete.
            print(f"Finished getting data for url {url}")
            url_queue.task_done()
        elif task == DOWNLOAD_COVER:
            url, filename = data
            print(f"Downloading cover to {filename}")
            MangaDB.download_cover(url, filename)
            url_queue.task_done()
        else:
            print("Didnt recognize task {task}!")


def single_thread_import(url_lists, url_queue, book_queue):
    # only the thread that created the sqlite conn can use it!!
    mdb = MangaDB(".", "manga_db.sqlite")

    while True:
        url, extr_data, thumb_url = book_queue.get()
        print(f"Adding book at {url}")
        # @Cleanup @Temporary convert lanugage in data to id
        extr_data["language_id"] = mdb.get_language(extr_data["language"])
        del extr_data["language"]

        book = Book(mdb, **extr_data)
        ext_info = ExternalInfo(mdb, book, **extr_data)
        book.ext_infos = [ext_info]
        book.list = url_lists[url]

        # @Cleanup @Temporary convert lanugage in data to id

        bid, outdated_on_ei_id = book.save(block_update=True)
        if bid is None:
            logger.info("Book at url '%s' was already in DB!",
                        url if url is not None else book.ext_infos[0].url)
            return None, None, None

        # book.save returns list of ext_info_ids but import book only ever has one
        # ext_info per book -> so later just return first one if true
        outdated_on_ei_id = outdated_on_ei_id[0] if outdated_on_ei_id else None

        cover_path = os.path.join(mdb.root_dir, "thumbs", f"{book.id}")
        url_queue.put((DOWNLOAD_COVER, (thumb_url, cover_path)))

        book_queue.task_done()

    # quque None NUMBER_OF_THREADS times so all url workers finish (since theyre not daemons
    # we have to end them otherwise program wont close)
    for i in range(NUMBER_OF_THREADS):
        url_queue.put((None, None))


def import_multiple(url_lists):
    url_queue = Queue()
    book_queue = Queue()
    print("** Filling URL Queue! **")
    for url, lists in url_lists.items():
        url_queue.put((RETRIEVE_BOOK_DATA, (url, lists)))

    print("** Starting threads! **")
    url_workers = []
    for i in range(NUMBER_OF_THREADS):
        t = Thread(
                name=f"URL-Worker {i}", target=thread_retrieve_data_or_cover,
                args=(url_queue, book_queue)
                )
        url_workers.append(t)
        t.start()

    importer = Thread(
            name="Importer", target=single_thread_import,
            # program may exit if there are only daemon threads left
            args=(url_lists, url_queue, book_queue), daemon=True
            )
    importer.start()

    print("** Waiting for threads to finish! **")
    # Blocks until all items in the queue have been gotten and processed
    # book_queue.join()

    for t in url_workers:
        print(f"Waiting for thread {t.name}")
        # Wait until the thread terminates
        t.join()

    print("** Done! **")
