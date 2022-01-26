import tkinter as tk
import tkinter.ttk as ttk
import ctypes
import python_env.views as views

class MyApplication(tk.Tk):
    """Main Application/Root window"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # set the window properties
        self.title("FAST - Flood Assessment Structure Tool")
        self.iconbitmap('./Images/Hazus.ico')

        # define the GUI/View
        views.GUI(self).grid(sticky='nsew')
        self.columnconfigure(0, weight=1) #fill in the space

if __name__ == "__main__":
    app = MyApplication()
    app.mainloop()
