# MangaDB
Local database with web front-end for managing mangas/doujins.

## Install
Download the source and start a shell in the root directory. Use
```
python -m pip install -r requirements.txt
```
to install the required 3rd-party packages.

## Usage
For using the WebGUI run the script like so:
```
run_manga_db.py webgui
```
Then you can access the WebGUI by going to `localhost:7578` in your web browser. The first time you access the WebGUI you have to create a user by clicking on **Register**. Then just type in the username and password combination you chose and press **Login**.

### Adding books
You can either import books from supported sites by pasting their URL into the search field and selecting **Import Book** or press the **+** symbol in the top right to add a book manually.

### Searching
The search bar matches the input string against the book's english and foreign title by default (so it if there's a string without a preceeding keyword the title is searched).

Additionally you can search the following fields:

| Field         | search keyword |
| -------------:| --------------:|
| Tags          | tag            |
| Artist        | artist         |
| Language      | language       |
| Group         | groups         |
| List          | list           |
| Collection    | collection     |
| (Title)       | title          |
All of these fields can be combined in one search. When the search string for a specific keyword contains spaces, it needs to be escaped with quotes. To search for multiple items that have to be present, separate them with semicolons.

E.g. this string searches for a book that has the tags Seinen and "Martial Arts" and is in the list "good":
```
list:good tag:"Seinen;Martial Arts"
```
#### Location of DB and thumbnails
To backup your installation of MangaDB you only need to copy the instance folder in the root directory. This is where your login info, all thumbnails and the database file is saved.

### Importing a lot of different mangas/doujins
Use:
```
run_manga_db.py link_collector
```
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