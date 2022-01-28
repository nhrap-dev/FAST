print('Starting FAST...')

import os
from os import listdir
from os.path import isfile, join
from pathlib import Path
import json
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import filedialog, Tcl
from tkinter import messagebox as messagebox
from threading import Thread
import ctypes
from .udf_field_mapping import map_udf_fields
from hazpy.flood import UDF

class GUI(tk.Frame):
    """ Create the controller frame """
    def __init__(self, *args):
        super().__init__()
        self.columnconfigure(0, weight=1)

        # Controller attributes   
        self.selected_flood_type = tk.StringVar() # string: Riverine, Coastal A, Coastal V
        self.selected_flood_type_converted = tk.StringVar() #HazardRiverine, V, CAE from lookup json; for use in udf

        self.selected_analysis_type = tk.StringVar() # string: Standard, AAL, AAL w/PELV; controls which raster frame to show

        self.selected_rasters_standard = [] # list of >= 1 rasters in C:\_repositories\Development\FAST\rasters
        self.selected_rasters_aal = {} # dictionary: return period:raster in C:\_repositories\Development\FAST\rasters
        self.selected_return_periods_aal = {}
        self.selected_raster_aal_pelv = tk.StringVar() # path to single 100yr raster in C:\_repositories\Development\FAST\rasters

        self.selected_udf = tk.StringVar() # path to csv file: C:\_repositories\Development\FAST\UDF\ND_Minot_UDF.csv
        self.selected_udf_fields_mapped = [] # List of tuples; of display name, udf field and required, updates when udf csv file selected
        self.selected_udf_fields_mapped_ordered = [] # ordered list of strings; of the mapped fields
        self.selected_udf_fields_required_mapped = tk.BooleanVar() #true if all required mapped fields are present

        self.rasters = self._load_rasters() #list of rasters from folder

        self._create_widgets()

    def _create_widgets(self):
        self.select_flood_type_frame = select_flood_type_frame(self).grid(column=0, row=0, sticky='new', padx=5, pady=5)
        self.select_analysis_type_frame = select_analysis_type_frame(self).grid(column=0, row=1, sticky='new', padx=5, pady=5)

        self.select_raster_aal_frame = select_raster_aal_frame(self)
        self.select_raster_aal_frame.grid(column=0, row=2, sticky='new', padx=5, pady=5)
        self.select_raster_aal_frame.grid_remove() # hide unless called
        self.select_raster_all_pelv_frame = select_raster_all_pelv_frame(self)
        self.select_raster_all_pelv_frame.grid(column=0, row=2, sticky='new', padx=5, pady=5)
        self.select_raster_all_pelv_frame.grid_remove() # hide unless called
        self.select_raster_standard_frame = select_raster_standard_frame(self)
        self.select_raster_standard_frame.grid(column=0, row=2, sticky='new', padx=5, pady=5)
        self.select_raster_standard_frame.grid_remove() # hide unless called
        self.select_raster_default = select_raster_default(self)
        self.select_raster_default.grid(column=0, row=2, sticky='new', padx=5, pady=5)

        self.select_udf_frame = select_udf_frame(self).grid(column=0, row=3, sticky='new', padx=5, pady=5)
        self.review_field_mapping_frame = review_field_mapping_frame(self).grid(column=0, row=4, sticky='new', padx=5, pady=5)
        self.bottom_buttons_frame = bottom_buttons_frame(self).grid(column=0, row=5, sticky='new', padx=5, pady=5)

    def _load_rasters(self):
        ''' Search rasters folder for all .tif files and make a listprint('Rasters selection ',rasters) '''
        dir = os.getcwd()
        if (dir.find('Python_env') != -1):
             dir = os.path.dirname(dir)
        cwd = os.path.join(dir,'rasters') # Default raster directory
        rasters = [f for f in listdir(cwd) if isfile(join(cwd, f)) and f.endswith(('.tif','.tiff','.nc'))] 
        rasters = Tcl().call('lsort', '-dict', rasters)
        return rasters

class select_flood_type_frame(ttk.Frame):
    ''' Riverine, Coastal A, Coastal V '''
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.columnconfigure(0, weight=1)
        self.flood_types = ["Coastal A", "Coastal V", "Riverine"] #TODO load from csv
        self._create_widgets()
        
    def _create_widgets(self):
        self.labelframe_floodtype = tk.LabelFrame(self, font=("Tahoma", "12"), labelanchor='nw', borderwidth=2)
        self.labelframe_floodtype.configure(text=' SELECT A FLOOD TYPE ')
        self.labelframe_floodtype.grid(column=0, row=0, sticky='ew')

        self.combobox_floodtype = ttk.Combobox(self.labelframe_floodtype, width=40)
        self.combobox_floodtype.configure(values=self.flood_types)
        self.combobox_floodtype.config(state='readonly')
        self.combobox_floodtype.bind("<<ComboboxSelected>>", self._set_floodtype)
        self.combobox_floodtype.bind("<<ComboboxSelected>>", self._set_selected_flood_type_converted, add="+")
        self.combobox_floodtype.grid(column=0, row=1, padx=5, pady=5)

    def _set_floodtype(self, *args):
        ''' '''
        self.controller.selected_flood_type.set(self.combobox_floodtype.get())
        print(f"Selection Flood Type: {self.controller.selected_flood_type.get()}")

    def _set_selected_flood_type_converted(self, *args):
        ''' Input into UDF requires specific flC values '''
        flood_type_lookup = self._get_json_data('hazard_types.json' )
        lookup_value = flood_type_lookup[self.controller.selected_flood_type.get()]
        self.controller.selected_flood_type_converted.set(lookup_value)
        print(f"Selection Flood Type Converted for UDF: {self.controller.selected_flood_type_converted.get()}")

    def _get_json_data(self, file):
        ''' Load a json file '''
        with open(os.path.join(Path(__file__).parent, file)) as json_file:
            data = json.load(json_file)
        return data

class select_analysis_type_frame(ttk.Frame):
    ''' Standard, AAL, AAL w/PELV 
        This determines which raster|depth grid frame to show
        When changed, clear the selected raster|depth grid string/list/dictionary
    '''
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.columnconfigure(0, weight=1)
        self.controller.analysis_types = ["Standard", "Average Annualized Loss (AAL)", "Average Annualized Loss (AAL) with PELV"] #TODO load from csv
        self._create_widgets()
        
    def _create_widgets(self):
        self.labelframe_analysistype = tk.LabelFrame(self, font=("Tahoma", "12"), labelanchor='nw', borderwidth=2)
        self.labelframe_analysistype.configure(text=' SELECT AN ANALYSIS TYPE ')
        self.labelframe_analysistype.grid(column=0, row=0, sticky='ew')

        self.combobox_analysistype = ttk.Combobox(self.labelframe_analysistype, width=40)
        self.combobox_analysistype.configure(values=self.controller.analysis_types)
        self.combobox_analysistype.config(state='readonly')
        self.combobox_analysistype.bind("<<ComboboxSelected>>", self._set_analysistype)
        self.combobox_analysistype.bind("<<ComboboxSelected>>", self._show_rasterframe, add="+")
        self.combobox_analysistype.grid(column=0, row=1, padx=5, pady=5)

    def _set_analysistype(self, *args):
        ''' '''
        self.controller.selected_analysis_type.set(self.combobox_analysistype.get())
        print(f"Selection Analysis Type: {self.controller.selected_analysis_type.get()}")

    def _clear_raster_selections(self):
        ''' Remove any selected hazards '''
        self.controller.selected_rasters_standard = []
        self.controller.selected_rasters_aal = {}
        self.controller.selected_raster_aal_pelv = tk.StringVar()

    def _hide_all_rasterframes(self, *args):
        ''' Hide all the rasterframes so that one can be shown
            Clear any selection in the frames 
        '''
        if self.controller.select_raster_default:
            self.controller.select_raster_default.grid_remove()
        if self.controller.select_raster_standard_frame:
            self.controller.select_raster_standard_frame.listbox_raster.selection_clear(0, tk.END)
            self.controller.select_raster_standard_frame.grid_remove()
        if self.controller.select_raster_aal_frame:
            #TODO clear aal selected rasters and entered return periods
            self.controller.select_raster_aal_frame.grid_remove()
        if self.controller.select_raster_all_pelv_frame:
            self.controller.select_raster_all_pelv_frame.listbox_raster.selection_clear(0, tk.END)
            self.controller.select_raster_all_pelv_frame.grid_remove()

    def _show_rasterframe(self, *args):
        ''' Show appropriate raster frame based on analysis type selected '''
        self._clear_raster_selections()
        self._hide_all_rasterframes()
        analysis_type = self.controller.selected_analysis_type.get()
        if analysis_type == 'Standard':
            self.controller.select_raster_standard_frame.grid()
        elif analysis_type == 'Average Annualized Loss (AAL)':
            self.controller.select_raster_aal_frame.grid()
        elif analysis_type == 'Average Annualized Loss (AAL) with PELV':
            self.controller.select_raster_all_pelv_frame.grid()

class select_raster_default(ttk.Frame):
    ''' Show something at start '''
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.columnconfigure(0, weight=1)
        self._create_widgets()

    def _create_widgets(self):
        self.labelframe_selectdefaultraster = tk.LabelFrame(self, font=("Tahoma", "12"), labelanchor='nw', borderwidth=2)
        self.labelframe_selectdefaultraster.configure(text=' SELECT DEPTH GRID(S) ')
        self.labelframe_selectdefaultraster.grid(column=0, row=0, sticky='ew')

        self.label_placeholder = tk.Label(self.labelframe_selectdefaultraster, text='First select an Analysis Type')
        self.label_placeholder.grid(column=1, row=0, sticky='w')

class select_raster_standard_frame(ttk.Frame):
    ''' one or more depth grids 
    TODO get actual file name not just position number
    '''
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.columnconfigure(0, weight=1)
        self._create_widgets()

    def _create_widgets(self):
        self.labelframe_selectstandardraster = tk.LabelFrame(self, font=("Tahoma", "12"), labelanchor='nw', borderwidth=2)
        self.labelframe_selectstandardraster.configure(text=' SELECT ONE OR MORE DEPTH GRID(S) ')
        self.labelframe_selectstandardraster.grid(column=0, row=0, sticky='ew')

        self.listbox_raster = tk.Listbox(self.labelframe_selectstandardraster, selectmode=tk.EXTENDED, exportselection=0, width=40, height=6)
        for num, raster in enumerate(self.controller.rasters): self.listbox_raster.insert(num, raster) #add rasters into listbox
        self.listbox_raster.bind("<<ListboxSelect>>", self._set_selected_rasters_standard)
        self.listbox_raster.grid(column=0, row=1, padx=5, pady=5)
        self.scrollbarRasters = tk.Scrollbar(self.labelframe_selectstandardraster)
        self.scrollbarRasters.grid(column=1, row=1, sticky='nsew')
        self.listbox_raster.config(yscrollcommand=self.scrollbarRasters.set)
        self.scrollbarRasters.config(command=self.listbox_raster.yview)

    def _set_selected_rasters_standard(self, *args):
        selected_rasters = []
        for i in self.listbox_raster.curselection():
            selected_rasters.append(self.listbox_raster.get(i))
        self.controller.selected_rasters_standard = (selected_rasters)
        print(f"Selected Rasters Standard: {', '.join(self.controller.selected_rasters_standard)}")


class select_raster_aal_frame(ttk.Frame):
    ''' minimum 3 depth grids, recommended 5 or more, allow at least 12 if cannot dynamically add more 
        Return period values set by user, can be a whole number from 1 to 10,0000 inclusive.
        TODO enable run only if three return periods and depth grids are entered/selected
    '''
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.columnconfigure(0, weight=1)
        self.rasters_dict = {}
        self.selected_return_periods = {}
        self.selected_rasters = {}
        self.comboboxes = {}
        self._create_widgets()

    def _validate_returnperiod_entry(self, P):
        ''' Limit the user to only enter in integers between 1 and 10,000 inclusive
        TODO this is validating each key entry, not the total entry so values above 10,000 are possible
        TODO turn this into a class'''
        def is_integer(n):
            ''' Determine if input n is an integer 
            returns boolean
            '''
            try:
                float(n)
            except ValueError:
                return False
            else:
                return float(n).is_integer()

        if is_integer(P):
            x = int(float(P))
            if x >= 1 and x <= 10000:
                return True
        elif P == "":
            return True
        else:
            return False

    def _create_widgets(self):
        self.labelframe_selectaalraster = tk.LabelFrame(self, font=("Tahoma", "12"), labelanchor='nw', borderwidth=2)
        self.labelframe_selectaalraster.configure(text=' ENTER RETURN PERIODS AND SELECT CORRESPONDING RASTERS ')
        self.labelframe_selectaalraster.grid(column=0, row=0, sticky='ew')

        label_text_a = 'For Return Period enter a number from 1 to 10,000.\nEnter and select at least three return period:raster pairings.'
        self.label_help = tk.Label(self.labelframe_selectaalraster, text=label_text_a, justify=tk.LEFT)
        self.label_help.grid(column=0, row=0, sticky='w', columnspan=3)

        #Create a canvas to hold a frame containing all of the label, entry, combobox widgets in a grid
        self.canvas = tk.Canvas(self.labelframe_selectaalraster, width=600, height=100) #create label, entry, combobox grid
        self.canvas.grid(column=0, row=1)
        self.scroll_y = tk.Scrollbar(self.labelframe_selectaalraster, orient="vertical", command=self.canvas.yview)
        self.scroll_y.grid(row=1, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scroll_y.set)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.canvas_frame = ttk.Frame(self.canvas, padding=5) #frame to contain widgets and placed into canvas

        self.canvas.create_window((4, 4), window=self.canvas_frame, anchor="nw")
        self.canvas_frame.bind("<Configure>", self.onFrameConfigure)

        vcmd = (self.register(self._validate_returnperiod_entry), '%P') #to limit user input to integers

        self.rp_names = [] #create an incremented list of return period names to reference
        self.labels = {} #dictionaries to reference the tkinter widget by rp_name from list above
        self.entries = {}
        self.comboboxes = {}
        self.return_periods = []
        self.selected_return_periods = {}
        self.selected_rasters = {}
        self.rasters = self.controller.rasters

        for x in range(1,13):
            self.rp_names.append(f"Return Period {x}")

        for i, name in enumerate(self.rp_names):
            # Create label, entrybox and combobox for user to input data and select raster(s)
            lab = tk.Label(self.canvas_frame, text=name+':')
            lab.grid(column=0, row=i, sticky='w')
            self.labels[name] = lab
            # Set return periods
            sv = tk.StringVar()
            sv.trace("w", lambda name, index, mode, sv=sv, i=i: self._set_return_periods(sv, index, i))
            ent = tk.Entry(self.canvas_frame, width=10, validate='key', textvariable=sv, validatecommand=vcmd)
            ent.grid(column=1, row=i, sticky='w')
            self.entries[name] = ent
            # Set rasters
            combo = ttk.Combobox(self.canvas_frame, width=65)
            combo.configure(values=self.controller.rasters)
            combo.config(state='readonly')
            combo.grid(column=2, row=i, sticky='w', padx=5, pady=5)
            self.comboboxes[name] = combo
            self.comboboxes[name].bind("<<ComboboxSelected>>", lambda event, i=i, raster=name: self._set_raster(event, i, raster))

    def _set_return_periods(self, sv, index, i):
        self.selected_return_periods[i] = sv.get()
        self.controller.selected_return_periods_aal[i] = self.selected_return_periods[i]
    
    def _set_raster(self, event, i, name):
        selected_raster = self.comboboxes[name].get()
        self.selected_rasters[i] = selected_raster
        self.controller.selected_rasters_aal[i] = selected_raster

    def onFrameConfigure(self, event):
        '''Reset the scroll region to encompass the inner frame'''
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

class select_raster_all_pelv_frame(ttk.Frame):
    ''' 1 depth grid that represents 100 year return period 
    TODO get actual file name not just position number'''
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.columnconfigure(0, weight=1)
        self._create_widgets()

    def _create_widgets(self):
        self.labelframe_selectdefaultraster = tk.LabelFrame(self, font=("Tahoma", "12"), labelanchor='nw', borderwidth=2)
        self.labelframe_selectdefaultraster.configure(text=' SELECT ONE DEPTH GRID REPRESENTING THE 100 YEAR RETURN PERIOD ')
        self.labelframe_selectdefaultraster.grid(column=0, row=0, sticky='ew')

        self.listbox_raster = tk.Listbox(self.labelframe_selectdefaultraster, selectmode=tk.BROWSE, exportselection=0, width=40, height=6)
        for num, raster in enumerate(self.controller.rasters): self.listbox_raster.insert(num, raster) #add rasters into listbox
        self.listbox_raster.bind("<<ListboxSelect>>", self._selected_raster_aal_pelv)
        self.listbox_raster.grid(column=0, row=1, padx=5, pady=5, sticky='nsew')
        self.scrollbarRasters = tk.Scrollbar(self.labelframe_selectdefaultraster)
        self.scrollbarRasters.grid(column=1, row=1, sticky='ns')
        self.listbox_raster.config(yscrollcommand=self.scrollbarRasters.set)
        self.scrollbarRasters.config(command=self.listbox_raster.yview)

    def _selected_raster_aal_pelv(self, *args):
        selection_number = self.listbox_raster.curselection()
        self.controller.selected_raster_aal_pelv.set(self.listbox_raster.get(selection_number))
        print(f"Selected Raster AAL PELV: {self.controller.selected_raster_aal_pelv.get()}")

class select_udf_frame(ttk.Frame):
    ''' choose csv file and display the path '''
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self._create_widgets()

    def _create_widgets(self):
        self.labelframe_selectudf = tk.LabelFrame(self, font=("Tahoma", "12"), labelanchor='nw', borderwidth=2)
        self.labelframe_selectudf.configure(text=' SELECT USER DEFINED FACILITIES (UDF) FILE ')
        self.labelframe_selectudf.grid(column=0, row=0, sticky='ew')

        self.button_selectudf = tk.Button(self.labelframe_selectudf, text="Browse to UDF (.csv) File", command=lambda:[self._select_udf(), self._set_udf_fields_mapped()])
        self.button_selectudf.grid(column=0, row=0, sticky='w', padx=5, pady=5)
        self.label_selectedudf = tk.Label(self.labelframe_selectudf, textvariable=self.controller.selected_udf)
        self.label_selectedudf.grid(column=1, row=0, sticky='ew')

    def _select_udf(self):
        ''' Browse window to select a UDF csv file '''
        initialdir = os.getcwd()
        if (initialdir.find('Python_env') != -1):
            initialdir = os.path.dirname(initialdir)    
        filename = filedialog.askopenfilename(initialdir = os.path.join(initialdir ,'UDF'), title="Select file", filetype=(("csv files","*.csv"),("all files","*.*"))) # Gets input csv file from user
        self.controller.selected_udf.set(filename)

    def _set_udf_fields_mapped(self):
        ''' Map the user selected fields using exernal module '''
        if self.controller.selected_udf.get() != '': #avoid error if user cancels file selection
            mapped_fields_list = map_udf_fields(self.controller.selected_udf.get())
            self.controller.selected_udf_fields_mapped = mapped_fields_list.mapped_fields #create list of tuples for iput into treeview widget
            self.controller.selected_udf_fields_mapped_ordered = mapped_fields_list.mapped_fields_ordered #create list of ordered fields for input to udf

            filename = self.controller.selected_udf.get() #TODO make the trace to update the treeview not so cludgy
            self.controller.selected_udf.set(filename) #to trigger trace, again
            print(f"Selected UDF: {self.controller.selected_udf.get()}")

class review_field_mapping_frame(ttk.Frame):
    ''' treeview showing default field, required, mapped udf field colorized '''
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.controller.selected_udf.trace_variable("w", self._trace_when_file_is_selected)
        self._create_widgets()

    def _create_widgets(self):
        ''' '''
        self.labelframe_mappedfields = tk.LabelFrame(self, font=("Tahoma", "12"), labelanchor='nw', borderwidth=2)
        self.labelframe_mappedfields.configure(text=' REVIEW FIELD MAPPING ')
        self.labelframe_mappedfields.grid(column=0, row=0, sticky='ew')

        #This is to get around the issue of tag_configure bg, fg not changing
        #However, it messes with the rest of the GUI style background colors if padding is used
        #https://stackoverflow.com/questions/61105126/tag-configure-is-not-working-while-using-theme-ttk-treeview
        self.style = ttk.Style(self)
        self.aktualTheme = self.style.theme_use()
        self.style.theme_create("dummy", parent=self.aktualTheme)
        self.style.theme_use("dummy")

        self.treeview_mappedfields = ttk.Treeview(self.labelframe_mappedfields, columns=(1,2,3), show='headings', selectmode='none')
        self.treeview_mappedfields.grid(column=0, row=1, sticky='ew')
        self.treeview_mappedfields.heading(1, text='FIELD', anchor='w')
        self.treeview_mappedfields.heading(2, text='MAPPED UDF FIELD', anchor='w')
        self.treeview_mappedfields.heading(3, text='REQUIRED', anchor='w')
        #self.treeview_mappedfields.insert(parent='', index=1, iid=1, text='', values=('test', '', 'test'), tags=('UnMatched','bogus')) #DEBUG

        self.treeview_mappedfields.tag_configure('Matched', background='#99CC00')
        self.treeview_mappedfields.tag_configure('UnMatchedNotRequired', background='#FFFF99')
        self.treeview_mappedfields.tag_configure('UnMatchedRequired', background='red')

        self.scrollbar_mappedfields = tk.Scrollbar(self.labelframe_mappedfields)
        self.scrollbar_mappedfields.grid(column=1, row=1, sticky='ns')
        self.treeview_mappedfields.config(yscrollcommand=self.scrollbar_mappedfields.set)
        self.scrollbar_mappedfields.config(command=self.treeview_mappedfields.yview)

        self.scrollbar_mappedfields_x = tk.Scrollbar(self.labelframe_mappedfields, orient='horizontal')
        self.scrollbar_mappedfields_x.grid(column=0, row=2, sticky='ew')
        self.treeview_mappedfields.config(xscrollcommand=self.scrollbar_mappedfields_x.set)
        self.scrollbar_mappedfields_x.config(command=self.treeview_mappedfields.xview)

        text_info = '''
        Fields named similar to defaults are search for.
        Red fields are required and must be mapped. 
        Green fields have been mapped successfully.
        Yellow fields have not been mapped, but are not required.
        '''
        self.label_info = tk.Label(self.labelframe_mappedfields, text=text_info, justify=tk.LEFT)
        self.label_info.grid(column=0, row=3, sticky='w')

    def _clear_mappedfields(self, *args):
        ''' Clear out the treeview widget entries '''
        #print('clear mapped fields treeview')
        self.treeview_mappedfields.delete(*self.treeview_mappedfields.get_children())

    def _load_mappedfields(self, list):
        ''' Load mapped fields into treeview widget '''
        self.controller.selected_udf_fields_required_mapped.set(True)
        counter = 0
        for row in list:
            if row[1] != '':
                tag = 'Matched'
            elif row[1] == '' and row[2] == 'Required':
                tag = 'UnMatchedRequired'
                self.controller.selected_udf_fields_required_mapped.set(False)
            elif row[1] == '' and row[2] == '':
                tag = 'UnMatchedNotRequired'
            else:
                tag = ''
            self.treeview_mappedfields.insert(parent='', index=counter, iid=counter, text='', values=(row[0], row[1], row[2]), tags=(tag,))
            counter +=1

    def _trace_when_file_is_selected(self, *args):
        ''' TODO '''
        #print('mapped fields trace')
        self._clear_mappedfields()
        self._load_mappedfields(self.controller.selected_udf_fields_mapped)


class bottom_buttons_frame(ttk.Frame):
    ''' Run analysis and Quit buttons 
        Run button is disabled until all options selected and all required fields are mapped
    '''
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.columnconfigure(0, weight=1)
        self._create_widgets()
        
    def _create_widgets(self):
        self.button_run = ttk.Button(self, text="Run") 
        self.button_run.configure(command=self._run)
        self.button_run.grid(column=0, row=0, sticky='e')

        self.button_quit = ttk.Button(self, text="Quit")
        self.button_quit.configure(command=self.controller.quit)
        self.button_quit.grid(column=1, row=0, sticky='w')

    def _run(self):
        ''' Check all inputs and run appropriate function based on analysis type
            If missing an input, prompt user with issue and don't run otherwise run
        '''
        print('--- CHECKING INPUT... ---')
        if self._check_selections() == True:
            print('--- RUNNING ---')
            flood_type = self.controller.selected_flood_type.get()
            flood_type_converted = self.controller.selected_flood_type_converted.get()
            analysis_type = self.controller.selected_analysis_type.get()
            udf = self.controller.selected_udf.get()
            arg_fields_list = self.controller.selected_udf_fields_mapped_ordered.copy() #avoid list mutation
            udf_args = []
            print(f"Selected Flood Type: {flood_type} Converted: {flood_type_converted}")
            print(f"Selected Analysis Type: {analysis_type}")
            print(f"Selected UDF: {udf}")
            print(f'Selected UDF Mapped and Ordered Fields: {arg_fields_list}')
            if self.controller.selected_analysis_type.get() == 'Standard':
                rasters = self.controller.selected_rasters_standard
                udf_args = arg_fields_list
                udf_args.append(flood_type_converted)
                udf_args.append(rasters)
                analysis_type = self.controller.selected_analysis_type.get()
                lookup_tables = os.path.join(os.getcwd(), 'lookuptables')
                results_dir = os.path.dirname(udf)
                fmap = udf_args[:-1]
                rasters = [os.path.join(os.getcwd(), 'rasters', raster) for raster in rasters]
                runUDF = UDF(udf, lookup_tables, results_dir, rasters, 'False', fmap, flood_type)
                runUDF.get_flood_damage()
            if self.controller.selected_analysis_type.get() == 'Average Annualized Loss (AAL)':
                rasters = [raster for raster in self.controller.selected_rasters_aal.values()]
                return_periods = [rp for rp in self.controller.selected_return_periods_aal.values()]
                print(f"Selected AAL Rasters: {', '.join(rasters)}")
                udf_args = arg_fields_list
                udf_args.append(flood_type_converted)
                udf_args.append(rasters)
                analysis_type = self.controller.selected_analysis_type.get()
                lookup_tables = os.path.join(os.getcwd(), 'lookuptables')
                results_dir = os.path.dirname(udf)
                fmap = udf_args[:-1]
                rasters = [os.path.join(os.getcwd(), 'rasters', raster) for raster in rasters]
                runUDF = UDF(udf, lookup_tables, results_dir, rasters, 'False', fmap, flood_type, analysis_type, return_periods)
                runUDF.get_flood_damage()
            if self.controller.selected_analysis_type.get() == 'Average Annualized Loss (AAL) with PELV':
                rasters = []
                raster = self.controller.selected_raster_aal_pelv.get()
                rasters.append(raster)
                print(f'''Selected Raster AAL PELV: {raster}''')
                udf_args = arg_fields_list
                udf_args.append(flood_type_converted)
                udf_args.append(rasters)
                analysis_type = self.controller.selected_analysis_type.get()
                lookup_tables = os.path.join(os.getcwd(), 'lookuptables')
                results_dir = os.path.dirname(udf)
                fmap = udf_args[:-1]
                rasters = [os.path.join(os.getcwd(), 'rasters', raster) for raster in rasters]
                print(f"Selected PELV Raster: {', '.join(rasters)}")
                runUDF = UDF(udf, lookup_tables, results_dir, rasters, 'False', fmap, flood_type, analysis_type)
                runUDF.get_flood_damage()

    def _check_selections(self):
        ''' Check if all selections are made, if not prompt user
            Return true unless missing a selection 
            TODO add user feedback that the tool is running
            See fielddisplay_order_for_udf.json for UDF arg field order
        '''
        good_to_go = True
        not_good_to_go_message = ""

        #Flood Type check
        if self.controller.selected_flood_type.get() == '':
            print("no flood type selected")
            good_to_go = False
            not_good_to_go_message = 'Please select a Flood Type.'

        #Analysis Type check; Not actually needed, just for raster selection
        if self.controller.selected_analysis_type.get() == '':
            print("no analysis type selected")
            good_to_go = False

        #Rasters check
        if self.controller.selected_analysis_type.get() == '':
            print("no analysis type nor raster selected")
            good_to_go = False
            not_good_to_go_message = not_good_to_go_message + os.linesep + "Please select an Analysis Type."
        if self.controller.selected_analysis_type.get() == 'Standard':
            if len(self.controller.selected_rasters_standard) == 0:
                print("no Standard raster(s) selected")
                good_to_go = False
                not_good_to_go_message = not_good_to_go_message + os.linesep + "Please select one or more depth grids."
        if self.controller.selected_analysis_type.get() == 'Average Annualized Loss (AAL)':
            if len(self.controller.selected_rasters_aal) < 3 :
                print("no AAL rasters selected")
                good_to_go = False
                not_good_to_go_message = not_good_to_go_message + os.linesep + "Please select three or more depth grids."
        if self.controller.selected_analysis_type.get() == 'Average Annualized Loss (AAL) with PELV':
            if self.controller.selected_raster_aal_pelv.get() == '':
                print("no AAL PELV raster selected")
                good_to_go = False
                not_good_to_go_message = not_good_to_go_message + os.linesep + "Please select a 100year depth grid."

        #UDF check
        if self.controller.selected_udf.get() == '':
            print("no UDF selected")
            good_to_go = False
            not_good_to_go_message = not_good_to_go_message + os.linesep + "Please select a UDF csv file."

        #Fields UnMatched Required check
        #if len(self.controller.selected_udf_fields_mapped_ordered) == 0: #This should be moot if UDF selected
        #    print("missing some or all required fields")
        if not self.controller.selected_udf_fields_required_mapped.get(): #boolean if a required field wasn't mapped
            good_to_go = False
            not_good_to_go_message = not_good_to_go_message + os.linesep + "Please modify your UDF .csv columns to match the required default fields."

        if good_to_go == True:
            print('All selections made. Good To Run.')
        else:
            print('All selections not made. NOT Good To Run.')
            print(not_good_to_go_message)
            self._popupmsg(not_good_to_go_message)

        return good_to_go

    def _popup(self, message):
        ''' Threaded popup for processing 
        TODO put into use or delete and remove ctypes and threaded imports '''
        popup_window = ctypes.windll.user32.MessageBoxW
        Thread(target = lambda :popup_window(None, f'{message}', 0)).start()

    def _popupmsg(self, msg, *args):
        """ Creates a tkinter popup message window

            Keyword Arguments:
                msg: str -- The message you want to display
        """    
        tk.messagebox.showinfo(message=msg)