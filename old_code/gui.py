import os
from tkinter import *
import webbrowser

from PIL import Image, ImageTk 
import pyperclip

from manga_db import load_or_create_sql_db, search_tags_string_parse

firefox_path="N:\_edc\FirefoxPortable\FirefoxPortable.exe"
# webbrowser apparently doesnt recognize any browsers on my sys, register one manually
# webbrowser.register(name, constructor[, instance])
webbrowser.register('firefox-port', None, webbrowser.BackgroundBrowser(firefox_path), 1)
BROWSER = webbrowser.get("firefox-port")


def round_up_div(x, y):
    # so we dont have to import math for ceil
    # The first part (21 // 5) becomes 4 and the second part evaluates to "True" if there is a remainder, which in addition True = 1; False = 0. So if there is no remainder, then it stays the same integer, but if there is a remainder it adds 1
    # src: user3074620, https://stackoverflow.com/questions/2356501/how-do-you-round-up-a-number-in-python
    return x // y + (x % y > 0)


class MangaDBGUI(Frame):
    def __init__(self, master=None):
        # pass master == parent frame or root Tk to Frame/super class
        super().__init__(master)
        self.grid(row=0, column=0, sticky=N+S+E+W)
        self.output_frame = None
        self.db_con, _ = load_or_create_sql_db("manga_db.sqlite")

        # configure the rows and columns to have a non-zero weight so that they will take up the extra space when expanding
        # for x in range(5):
        #     Grid.columnconfigure(self, x, weight=1, pad=3)

        # for y in range(5):
        #     Grid.rowconfigure(self, y, weight=1, pad=3)
        self.search_descr = Label(self, text="Search for tags, seperate them with commas:", justify=LEFT)
        # sticky -> alignment in N S W E
        self.search_descr.grid(row=0, pady=1, padx=1)
        self.search_field = Entry(self)
        # exec func search_for_tags when Return is pressed
        self.search_field.bind("<Return>", self.search_for_tags)
        # margin -> use grid with padx, pady; (inner) padding -> create widget with padx, pady
        self.search_field.grid(row=1, sticky=W+E, padx=5, pady=1)

        # command=lambda e=search_field: print(e.get()) lambda: search_for_tags(e))
        self.search_btn = Button(self, text="Search!", command=self.search_for_tags)
        self.search_btn.grid(row=1, column=1, padx=1, pady=1)

        self.output_frame = SearchResultOutput(self, 2, 0, (3,3))

    def search_for_tags(self, event=None):
        # event z.B. <KeyPress event state=Mod1 keysym=Return keycode=13 char='\r' x=46 y=12>
        # print(event, self.search_field.get())
        self.output_frame.search(self.search_field.get())


class SearchResultOutput(Frame):
    def __init__(self, master, row, col, grid_dimensions):
        super().__init__(master)
        self.grid(row=row, column=col, columnspan=2, sticky=N+W)
        # Grid.rowconfigure(self, 0, weight=1)
        # Grid.columnconfigure(self, 0, weight=1)
        self.img_grid_frame = None
        self.colmax, self.rowmax = grid_dimensions
        self.img_grid_widgets = []
        self.init_output()
        # track index in data of first grid item displayed
        self.current_i = 0
        self.data = None
        self.max_pages = 0
        self.back_btn = Button(self, text="Back", command=None, justify=LEFT, fg="grey")
        self.back_btn.grid(row=1, column=0)
        self.next_btn = Button(self, text="Next", command=None, justify=RIGHT, fg="grey")
        self.next_btn.grid(row=1, column=2)
        self._pg_spinval_old = None
        self.pg_spinval = IntVar()
        self.pg_spinbox = Spinbox(self, textvariable=self.pg_spinval, justify=CENTER, command=self.pg_spinbox_action)
        self.pg_spinbox.bind("<Return>", self.pg_spinbox_action)
        self.pg_spinbox.grid(row=1, column=1)

    def search(self, tagstring):
        # reset page i
        self.current_i = 0
        # sqlite3.Row objects returned -> columns accessible like a dictionary
        self.data = search_tags_string_parse(self.master.db_con, tagstring)
        self.max_pages = round_up_div(len(self.data), self.rowmax*self.colmax)
        # greyed out buttons if results fit page and no action on click
        if self.max_pages == 1:
            self.back_btn.config(fg="grey", command=None)
            self.next_btn.config(fg="grey", command=None)
        else:
            self.next_btn.config(fg="black", command=self.next_pg)
        # account for not getting any data back -> max_pages 0 so from also has to be 0
        from_i = 1 if self.data else 0
        self.pg_spinbox.config(from_=from_i, to=self.max_pages)
        self._pg_spinval_old = 1
        self.pg_spinval.set(f"{from_i} of {self.max_pages}")

        self.generate_output()

    def pg_spinbox_action(self, *args):
        new_pg = self.pg_spinval.get()
        if new_pg == self._pg_spinval_old + 1:
            self.next_pg()
        elif new_pg == self._pg_spinval_old - 1:
            self.back_pg()
        else:
            self.jump_pg(new_pg)

    def jump_pg(self, new_pg):
        # spinbox from-to alrdy makes sure that pg nr is valid
        self.current_i = (new_pg - 1) * (self.rowmax * self.colmax)
        self._pg_spinval_old = new_pg 
        self.pg_spinval.set(f"{self._pg_spinval_old} of {self.max_pages}")
        self.set_pg_btn_status()
        self.generate_output()

    def next_pg(self):
        # at least one item left
        if (self.current_i+self.rowmax*self.colmax) < len(self.data):
            self.current_i += self.rowmax*self.colmax
            self._pg_spinval_old += 1
            self.pg_spinval.set(f"{self._pg_spinval_old} of {self.max_pages}")
            self.set_pg_btn_status()
            self.generate_output()

    def back_pg(self):
        # print(self.winfo_width(), self.winfo_height())
        # return
        if self.current_i > 0:
            self.current_i -= self.rowmax*self.colmax
            self._pg_spinval_old -= 1
            self.pg_spinval.set(f"{self._pg_spinval_old} of {self.max_pages}")
            self.set_pg_btn_status()
            self.generate_output()

    def set_pg_btn_status(self):
        """Sets status of back and next buttons (greyed out and no effect when no more pages
           that direction)"""
        data_len = len(self.data)
        if self.current_i == 0:
            self.back_btn.config(fg="grey", command=None)
        else:
            self.back_btn.config(fg="black", command=self.back_pg)

        if (self.current_i+self.rowmax*self.colmax) >= data_len:
            self.next_btn.config(fg="grey", command=None)
        else:
            self.next_btn.config(fg="black", command=self.next_pg)

    def init_output(self):
        self.img_grid_frame = Frame(self, relief=SUNKEN, bg="white", borderwidth=1, padx=5, pady=5,
                width=435, height=685)
        self.img_grid_frame.grid(row=0, column=0, columnspan=self.colmax, sticky=N+W, padx=5, pady=5)
        # setting size when creating instance of Frame and turning of propagate -> Frame will stay the same size and wont resize to fit content
        self.img_grid_frame.grid_propagate(0)
        # create grid with grid_dimensions with title+image placeholders (-> rows*2)
        for row_index in range(0, self.rowmax):
            Grid.rowconfigure(self.img_grid_frame, row_index, weight=1)
            row_list = []
            for col_index in range(self.colmax):
                Grid.columnconfigure(self.img_grid_frame, col_index, weight=1, pad=3)
                # line-wrapping -> wraplenght kw param, the units for this are screen units so try wraplength=50 and adjust as necessary. You will also need to set "justify" to LEFT, RIGHT or CENTER
                # compound -> behaviour when both txt and img present, default display img instead of txt
                # TOP -> draw img above text, anchor=N -> place img+txt anchored at top
                # -> this way only one label widget needed instead of 2; other solution also wasnt working since: If the label displays text, the size is given in text units. If the label displays an image, the size is given in pixels (or screen units). If the size is set to 0, or omitted, it is calculated based on the label contents. 
                # set width so we get correct placement even if not all grid positions are used (less than one full page) -> not using height=x works since we use anchor=N and it gets placed topmost
                # -> placement was still off for long txt etc.
                l = Label(self.img_grid_frame, bg="white", width=1, wraplength=125,
                        compound=TOP, pady=3, justify=CENTER, anchor=N)

                l.grid(row=row_index, column=col_index, sticky=N+S+E+W)  
                row_list.append(l)

            self.img_grid_widgets.append(row_list)

    def generate_output(self):
        for row_index in range(0, self.rowmax):
            for col_index in range(self.colmax):
                label = self.img_grid_widgets[row_index][col_index]
                data_index = self.current_i + self.colmax*row_index + col_index
                # run out of items?
                if data_index >= len(self.data):
                    # remove images (and all references to it so it get gc'ed) and text from unused widgets
                    label.configure(image=None, text="")
                    label.image = None
                    # remove all callbacks for Button-1 event
                    label.unbind("<Button-1>")
                    label.unbind("<Button-2>")
                else:
                    # :.40 truncate to 40 chars
                    text = f"{self.data[data_index]['title_eng']:.40}..." if len(self.data[data_index]['title_eng']) > 39 else self.data[data_index]['title_eng']

                    img = Image.open(os.path.join("thumbs", f"{self.data[data_index]['id_onpage']}"))

                    # change size of img with PIL/pillow b4 creating PhotoImage
                    # 400, 562; 200, 281; width*1.405=height
                    img = img.resize((125, 176), Image.ANTIALIAS) #The (250, 250) is (height, width)
                    tkimage = ImageTk.PhotoImage(img)
                    label.configure(image=tkimage, text=text)

                    # 1->LMB 2->middleMB 3->RMB
                    # assign data_index to i in lambda so we can use it later, otherwise the latest data_index which is always (rowmax*colmax)-1 will be used
                    label.bind("<Button-1>", lambda e,i=data_index: pyperclip.copy(f"{self.data[i]['url']}"))
                    label.bind("<Button-2>", lambda e,i=data_index: BROWSER.open_new_tab(f"{self.data[i]['url']}"))
                    # Note: When a PhotoImage object is garbage-collected by Python (e.g. when you return from a function which stored an image in a local variable), the image is cleared even if it’s being displayed by a Tkinter widget.
                    # To avoid this, the program must keep an extra reference to the image object. A simple way to do this is to assign the image to a widget attribute, like this:
                    label.image=tkimage


root = Tk()
root.wm_title("MangaDB")
# root.iconbitmap(default='icon.ico')
root.rowconfigure(0, weight=1)
root.columnconfigure(0, weight=1)
# limitting size of window
#root.minsize(width=666, height=666)
# root.maxsize(width=666, height=666)
# dont allow resizing (user)
root.resizable(width=False, height=False)
# then change window size in code with
root.geometry('445x780')

# sizes search only, with result, optimum: 302x86 493x905 493x803

main_frame = MangaDBGUI(root)

root.mainloop()
