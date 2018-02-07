import os
from tkinter import *

from PIL import Image, ImageTk 

from manga_db import load_or_create_sql_db, search_tags_intersection


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
        self.output_frame.search(self.search_field.get().split(", "))


class SearchResultOutput(Frame):
    def __init__(self, master, row, col, grid_dimensions):
        super().__init__(master)
        self.grid(row=row, column=col, columnspan=2, sticky=N+W)
        # Grid.rowconfigure(self, 0, weight=1)
        # Grid.columnconfigure(self, 0, weight=1)
        self.img_grid_frame = None
        self.colmax, self.rowmax = grid_dimensions
        # track index in data of first grid item displayed
        self.current_i = 0
        self.data = None
        self.back_btn = None
        self.next_btn = None

    def search(self, tags):
        # sqlite3.Row objects returned -> columns accessible like a dictionary
        self.data = search_tags_intersection(self.master.db_con, tags)
        # no buttons if results fit page
        if len(self.data) > (self.rowmax*self.colmax):
            self.back_btn = Button(self, text="Back", command=self.back_pg, justify=LEFT)
            self.back_btn.grid(row=1, column=0)
            self.next_btn = Button(self, text="Next", command=self.next_pg, justify=RIGHT)
            self.next_btn.grid(row=1, column=2)
        self.generate_output()

    def next_pg(self):
        # at least one item left
        if (self.current_i+self.rowmax*self.colmax) < len(self.data):
            self.current_i += self.rowmax*self.colmax
            self.generate_output()

    def back_pg(self):
        # print(self.winfo_width(), self.winfo_height())
        # return
        if self.current_i > 0:
            self.current_i -= self.rowmax*self.colmax
            self.generate_output()

    def generate_output(self):
        # destroy old output first -> otherwise kept in mem
        if self.img_grid_frame:
            self.img_grid_frame.destroy()
        self.img_grid_frame = Frame(self, relief=SUNKEN, bg="white", borderwidth=1, padx=5, pady=5)
        self.img_grid_frame.grid(row=0, column=0, columnspan=self.colmax, sticky=N+W, padx=5, pady=5)
        # create grid with grid_dimensions with title+image (-> rows*2)
        # convert i-th item to row i//3*2
        row_start = self.current_i//3*2
        for row_index in range(row_start, row_start+self.rowmax*2, 2):
            Grid.rowconfigure(self.img_grid_frame, row_index, weight=1)
            Grid.rowconfigure(self.img_grid_frame, row_index+1, weight=1)
            for col_index in range(self.colmax):
                # two rows per item (title+img) -> current item index: row_index//2*self.colmax+col_index
                index = row_index//2*self.colmax+col_index
                # run out of items?
                if index >= len(self.data):
                    return

                Grid.columnconfigure(self.img_grid_frame, col_index, weight=1, pad=3)
                img = Image.open(os.path.join("thumbs", f"{self.data[index]['id_onpage']}"))

                # change size of img with PIL/pillow b4 creating PhotoImage
                # 400, 562; 200, 281; width*1.405=height
                img = img.resize((125, 176), Image.ANTIALIAS) #The (250, 250) is (height, width)
                tkimage = ImageTk.PhotoImage(img)
                l = Label(self.img_grid_frame, image=tkimage, bg="white")
                # Note: When a PhotoImage object is garbage-collected by Python (e.g. when you return from a function which stored an image in a local variable), the image is cleared even if it’s being displayed by a Tkinter widget.
                # To avoid this, the program must keep an extra reference to the image object. A simple way to do this is to assign the image to a widget attribute, like this:
                l.image=tkimage

                # line-wrapping -> wraplenght kw param, the units for this are screen units so try wraplength=50 and adjust as necessary. You will also need to set "justify" to LEFT, RIGHT or CENTER
                text = f"{self.data[index]['title_eng']:.45}..." if len(self.data[index]['title_eng']) > 44 else self.data[index]['title_eng']
                t = Label(self.img_grid_frame, text=text, bg="white", wraplength=150, justify=CENTER)#"Title!")
                l.grid(row=row_index+1, column=col_index, sticky=N+S+E+W)  
                t.grid(row=row_index, column=col_index, sticky=N+S+E+W)  
        # print childs of
        # print(main_frame.winfo_children())


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
root.geometry('445x770')

# sizes search only, with result, optimum: 302x86 493x905 493x803

main_frame = MangaDBGUI(root)

root.mainloop()
