import os
import time
import logging
from threading import Thread, current_thread
from queue import Queue

from .manga_db import MangaDB
from .manga import Book
from .ext_info import ExternalInfo

logger = logging.getLogger(__name__)

NUMBER_OF_THREADS = 3
URL_WORKER_SLEEP = 1
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
            url_queue.task_done()
        elif task == DOWNLOAD_COVER:
            url, filename = data
            print(f"Downloading cover to {filename}")
            MangaDB.download_cover(url, filename)
            url_queue.task_done()
        else:
            print("Didnt recognize task {task}!")
        time.sleep(URL_WORKER_SLEEP)


def single_thread_import(url_lists, to_process, url_queue, book_queue):
    # only the thread that created the sqlite conn can use it!!
    mdb = MangaDB(".", "manga_db.sqlite")

    processed = 0
    while True:
        url, extr_data, thumb_url = book_queue.get()
        processed += 1
        print(f"Adding book at {url}")
        # @Cleanup @Temporary convert lanugage in data to id
        extr_data["language_id"] = mdb.get_language(extr_data["language"])
        del extr_data["language"]

        book = Book(mdb, **extr_data)
        ext_info = ExternalInfo(mdb, book, **extr_data)
        book.ext_infos = [ext_info]
        book.list = url_lists[url]

        bid, outdated_on_ei_id = book.save(block_update=True)
        if bid is None:
            logger.info("Book at url '%s' was already in DB!",
                        url if url is not None else book.ext_infos[0].url)
            # also counts as processed/done
            book_queue.task_done()
            continue

        cover_path = os.path.join(mdb.root_dir, "thumbs", f"{book.id}")
        url_queue.put((DOWNLOAD_COVER, (thumb_url, cover_path)))

        book_queue.task_done()
        if processed == to_process:
            # send url workers signal to stop
            for i in range(NUMBER_OF_THREADS):
                url_queue.put((None, None))
            break
        time.sleep(0.1)


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

    # importer thread counts process urls/books and stops
    to_process = len(url_lists)
    # only one thread writes to db
    importer = Thread(
            name="Importer", target=single_thread_import,
            # program may exit if there are only daemon threads left
            args=(url_lists, to_process, url_queue, book_queue)
            )
    importer.start()

    print("** Waiting for threads to finish! **")

    for t in url_workers:
        print(f"** Waiting on thread {t.name} **")
        t.join()

    print("** Done! **")
