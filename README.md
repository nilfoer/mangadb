# MangaDB
Local database including a web front-end for managing mangas/doujinshi.

## WebGUI preview
The previews are taken from a desktop PC, but the site is responsive and can be used just as well on a mobile device!

### Main page
![MangaDB webGUI main page](https://i.imgur.com/c0Za7oG.jpg)


### Book page
![MangaDB book page](https://i.imgur.com/6JUEQfJ.png)

## Installation
Download the latest release  of your choice [here](https://github.com/nilfoer/mangadb/releases) (the standalone version is recommended for not so tech-savy people). For more advanced users that want to clone this repo: Keep in mind that third-party dependencies as well as the `.css` file that was generated from SASS are **not** checked into git!

### Standalone zip

All dependencies are included and contained in the zip file. Just extract to contents and run the `MangaDB.exe` with:
```
MangaDB.exe -h
```
to show the available commands! Most users will just want to start the webGUI using `MangaDB.exe webgui`.

The webGUI will automatically create an `instance` folder inside the directory of the executable where the database, config and thumb images will be stored.

### Source zip including third-party dependencies

All third-party dependencies that can't be aquired over `pip` are included in the zip archive. For the ones that can be, use:
```
python -m pip install -r requirements.txt
```

Installing MangaDB to your site-packages is not recommended but if you want to, you can:
```
python -m pip install .
```
When starting MangaDB you should then specify a custom path using `manga_db -p /your/path` otherwise Flask, which is used by MangaDB for the webGUI will store your user data in `$PREFIX/var/manga_db.webGUI-instance`, where `$PREFIX` is the prefix of your Python installation. For more information have a look at [Flask's documentation](https://flask.palletsprojects.com/en/1.0.x/config/#instance-folders).

## Usage

If you are not using the default `instance` directory in the same path where the executable or `run_manga_db.py` are stored (the *instance* folder is where the database file and the thumbs are located) you  need to pass it to MangaDB using `-p /your/path`. (See above for where the webGUI stores user files in the case it's installed as a python package)

For using the WebGUI run the script like so (replace `MangaDB.exe` with `run_manga_db.py` if you are using the source zip version):
```
MangaDB.exe webgui
```

Then you can access the WebGUI by going to `localhost:7578` (7578 is the default port) in your web browser. The first time you access the WebGUI you have to create a user by clicking on **Register**. Then just type in the username and password combination you chose and press **Login**.

To be able to access the site with e.g. your phone in your LAN use `MangaDB.exe webgui --open` and then browse to http://INSERT.YOUR.IP.HERE:7578/

### Adding books
You can either import books from supported sites by pasting their URL into the search field and selecting **Import Book** or press the **+** symbol in the top right to add a book manually.

### Searching
The search bar matches the input string against the book's english and foreign title by default (so it if there's a string without a preceeding keyword the title is searched).

Additionally you can search the following fields:

| Field          | Search keyword | Possible values               |
|:-------------- |:-------------- | -----------------------------:|
| Tags           | tag            |                    Any string |
| Artist         | artist         |                    Any string |
| Language       | language       |                    Any string |
| Group          | groups         |                    Any string |
| List           | list           |                    Any string |
| Collection     | collection     |                    Any string |
| Category       | category       |                    Any string |
| Status         | status         |   Unknown, Completed, Ongoing |
|                |                | Unreleased, Hiatus, Cancelled |
| Parody         | parody         |                    Any string |
| Character      | character      |                    Any string |
| Favorite       | favorite       |                        0 or 1 |
| Content Rating | nsfw           |                        0 or 1 |
| Read status    | read\_status   |         read, reading, unread |
| (Title)        | title          |     Any string, partial match |

All of these fields can be combined in one search. When the search string for a specific keyword contains spaces, it needs to be escaped with quotes. To search for multiple items that have to be present, separate them with semicolons.

E.g. this string searches for a book that has the tags Seinen and "Martial Arts" and is in the list "good":
```
list:good tag:"Seinen;Martial Arts"
```

Search for sfw favorites in the 'Manga' (search is **case-sensitive**) category:
```
category:Manga favorite:1 nsfw:0
```

Display 'Seinen' mangas you're currently reading:
```
read_status:reading tag:Seinen
```
*Note: read\_status currently doesn't respect 'Chapter status'. So in order to mark a book as __'reading'__
you have to set the 'Read status' to a __non-zero value__. To mark a book as __'read'__ set 'Read status'
to __zero__.*

#### Location of DB and thumbnails
To backup your installation of MangaDB you only need to copy the instance folder in the directory where either the `MangaDB.exe` or the `run_manga_db.py` is located. The 'instance' directory is where your login info, all thumbnails and the database file is saved.

### Importing a lot of different mangas/doujinshi
Use:
```
MangaDB.exe link_collector
```
(When used with source zip version you need to specify the path to your `instance` folder, where the database file and the thumbs directory are located: e.g. `run_manga_db.py -p ./instace`)

To add a single link use the command
```
add URL [list [list]...]
```
if downloaded is among the lists, the downloaded option will be set on the external link.

The best way of adding a lot of books is using the command `collect` which will watch the clipboard for supported URLs and add them to the import list. If you want to add all of the added books to certain lists, use `set_standard_lists [lists [list]...]`, these will be added to all following books from that point on.

To change lists on added links use:
```
set_lists(sl) URL/r(ecent) [list [list]...]
```
`r` or `recent` as first argument sets the lists on the most recent book (works on most commands).

Set book as not downloaded:
```
not_downloaded(ndl) URL/r(ecent)
```
Remove book:
```
remove URL/r(ecent)
```
`export` writes current state of added links to `link_collect_resume.json`, which can be used to resume at this state when starting the script with `run_manga_db.py link_collector --resume`

Use `p(rint)` with no argmuent to print the most recent book, `p URL` to print the book with that URL or `p all` to print all books.

When your're finished use `import` to start importing books.
