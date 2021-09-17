import os
from pathlib import Path
import csv
import json

class map_udf_fields():
    ''' Create a dictionary of mapped UDF fields to Default Fields '''
    def __init__(self, file_path):
        ''' The file path is the csv file '''
        self.file_path = file_path #UDF csv file
        self.file_fields = self._get_file_fields() # list

        self.field_lookup_path = 'field_lookup.json' # should be in python_env
        self.field_lookup = self._get_json_data(self.field_lookup_path) # dict

        self.field_names_path = 'field_names.json' # should be in python_env
        self.field_names = self._get_json_data(self.field_names_path) # dict

        self.fields_required_path = 'fields_required.json' # should be in python_env
        self.fields_required = self._get_json_data(self.fields_required_path) # dict

        self.mapped_fields = self._map_udf_fields() # dict #May not be needed?


    def _get_file_fields(self):
        ''' TODO '''
        with open(self.file_path, 'r') as f:
            csv_reader = csv.DictReader(f)
            dict_from_csv = dict(list(csv_reader)[0])
            list_of_column_names = list(dict_from_csv.keys())
        return list_of_column_names
    
    def _get_json_data(self, file):
        ''' Load a json file '''
        with open(os.path.join(Path(__file__).parent, file)) as json_file:
            data = json.load(json_file)
        return data

    def _map_udf_fields(self):
        ''' Create a list of tuples containing the display field name, 
            the mapped udf field and if the field is required.

        Returns:
            tuple
            (Field_Name, UDF_Field, Required)
            i.e. (Specific Occupancy ID, 'SOID', 'Required')
        '''
        mapped_fields = []
        for field in self.field_lookup.items():
            field_name = self.field_names[field[0]] #get display name
            matched_file_field = ''
            required = ''
            lookup_list = field[1] #possible field names
            for file_field in self.file_fields:
                if file_field in lookup_list:
                    matched_file_field = file_field #UDF csv field that matched a lookup value
            for field_id in self.fields_required.items():
                if field_id[0] == field[0] and field_id[1] == 1:
                    required = 'Required'

            mapped_fields.append((field_name, matched_file_field, required))

        return mapped_fields




        ''' TODO 
        UDF input needs to be: it looks like a positional entry on line 87 in UDF.py
        It appears fields need to be passed into UDF in a specific order:
        UserDefinedFltyId,
        OccupancyClass,
        Cost,
        Area,
        NumStories,
        FoundationType,
        FirstFloorHt,
        ContentCost,
        BldgDamageFnID,
        ContDamageFnId,
        InvDamageFnId,
        InvCost,
        SOI,
        latitude,
        longitude,
        flC
        '''
        


if __name__ == "__main__":
    file_path = r'C:\_repositories\Development\FAST\UDF\HI_Honolulu_UDF.csv'
    x = map_udf_fields(file_path)
  
    if 1 > 0:
        print(x.file_fields)
        print()
        for y in x.mapped_fields:
            print(y)

    if 1 < 0:
        print(x.file_path)
        print()
        print(x.file_fields)
        #print()
        #print(x.field_lookup)
        print()
        print(x.field_lookup.keys())
        print()
        print(x.field_lookup.values())
        print()
        print(x.field_lookup['UserDefinedFltyId'])
        print()

