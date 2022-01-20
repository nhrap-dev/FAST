from hazpy.flood.modules import AAL
from hazpy.flood.modules import PELV
from rasterio.features import shapes

import geopandas as gpd
import logging
import math
import numpy as np
import os
import pandas as pd
import rasterio as rio
import sys
import time
import warnings

# Disable pandas warnings
warnings.filterwarnings('ignore')


class UDF:
    def __init__(
        self,
        UDFOrig,
        LUT_Dir,
        ResultsDir,
        DepthGrids,
        QC_Warning,
        fmap,
        flood_type,
        analysis_type=None,
        return_periods=None,
    ):
        self.UDFOrig = UDFOrig
        self.LUT_Dir = LUT_Dir
        self.ResultsDir = ResultsDir
        self.DepthGrids = DepthGrids
        self.QC_Warning = QC_Warning
        self.fmap = fmap
        self.flood_type = flood_type
        self.analysis_type = analysis_type
        self.return_periods = return_periods
        self.cdir = os.getcwd()

    def adjust_depths(self, raster, pelv_depth=None):
        if pelv_depth:
            fn_depth_grid = lambda row: row['Depth_Grid'] - float(row['FirstFloorHt']) if row['Depth_Grid'] >= 0 else row['Depth_Grid']
            raster['Depth_Grid'] = (raster[pelv_depth] + raster['Depth']).astype(str).str.slice(0, 15).astype(float).round(6)
            raster['Depth_in_Struc'] = raster.apply(fn_depth_grid, axis=1).astype(str).str.slice(0, 15).astype(float).round(6)
            # Check if UDF in the specified floodplain (Boolean)
            raster['flExp'] = raster.apply(lambda x: 1 if x['Depth_in_Struc'] != -3.402823 else 0, axis=1) #TODO Review this
            raster.drop(['index_right', 'Depth', 'geometry'], axis=1, inplace=True)
        else:
            fn_depth_grid = lambda row: row['Depth'] - float(row['FirstFloorHt']) if row['Depth'] >= 0 else row['Depth']
            raster['Depth_Grid'] = raster['Depth'].astype(str).str.slice(0, 15).astype(float).round(6)
            raster['Depth_in_Struc'] = raster.apply(fn_depth_grid, axis=1).astype(str).str.slice(0, 15).astype(float).round(6)
            # Check if UDF in the specified floodplain (Boolean)
            raster['flExp'] = raster.apply(lambda x: 1 if x['Depth_in_Struc'] != -3.402823 else 0, axis=1) #TODO Review this
            raster.drop(['index_right', 'Depth', 'geometry'], axis=1, inplace=True)
        return raster

    def change_directory(self):
        if self.cdir.find('Python_env') != -1:
            self.cdir = os.path.dirname(self.cdir)

    def check_utm(self, raster):
        is_utm = True if raster.crs.linear_units == 'metre' else False
        return is_utm

    def check_fields(self, input_fields, required_fields):
        """
        Check for user-supplied fields
    """
        field_check = all(item in required_fields for item in input_fields)
        return field_check

    def check_values(self, table):
        """
        Check for user-supplied values
    """
        pass

    def create_geo_df(self, input):
        crs = {'init': 'epsg:4326'}
        gdf = gpd.GeoDataFrame(
            input, geometry=gpd.points_from_xy(input.Longitude, input.Latitude, crs=crs))
        return gdf

    def create_somid(self, occ, num_stories):
        if occ[:4] == 'RES3':
            # RES3 has three categories: 1 3 5
            somid = ('5' if num_stories > 4 else '3' if num_stories > 2 else '1')
        elif occ[:4] == 'RES1':
            # If NumStories is not an integer, assume Split Level residence
            # Also, cap it at 3.
            somid = str(round(num_stories) if num_stories - round(num_stories) == 0 else 'S')
        elif occ[:4] == 'RES2':
            # Manuf. Housing is by definition limited to one story
            somid = '1'
        else:
            # All other cases: 1-3, 4-7, 8+
            somid = ('H' if num_stories > 6 else 'M' if num_stories > 3 else 'L')
        return somid

    def create_specific_occ_id(self, df):
        # Apply function to data frame rows
        df['sopre'] = [i[:1] + i[-(len(i) - 3) :] if i != 'REL1' else 'RE1' for i in df['Occ']]
        df['somid'] = [self.create_somid(occ, num_stories) for occ, num_stories in zip(df['Occ'], df['NumStories'])]
        df['sosuf'] = np.where(df['FoundationType'] == 4, 'B', 'N')
        fn = lambda row: row['sopre'] + row['somid']  + row['sosuf']
        df['SOID'] = df.apply(fn, axis=1)
        df.drop(
           ['sopre', 'somid', 'sosuf'],
            axis=1,
            inplace=True,
        )
        return df

    def get_field_names(self, input):
        """
        Get and assign field names
        # TODO: Break this out (normalize) to call other functions
        # TODO: Read csv into a pandas dataframe
    """
        # with open(self.UDFOrig, "r+") as f:
            # reader = csv.reader(f)
            # field_names = next(reader)
            # # f.close()
        field_names = list(input.columns)
            #########################################################################################################
            # UDF Input Attributes. The following are standard Hazus names/capitalizations.
            #########################################################################################################
            # [map for map in fmap if map != '' else]#[value if value != '' and any(value in s for s in field_names) == True else field for field, value in fmap]
        (
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
            flC,
        ) = self.fmap
        #return self.fmap
        return field_names

    def get_flood_damage(self):
        # https://gdal.org/user/configoptions.html
        logger = logging.getLogger('FAST')
        logger.setLevel(logging.INFO)
   #     self.log_messages()
   #     self.create_message()
            # if cdir.find('Python_env') != -1:
            #     cdir = os.path.dirname(cdir)
        self.change_directory()
        logDirName = "Log"
   #     logDir = os.path.join(cdir, logDirName)

 #       handler = logging.FileHandler(logDir + '\\' + 'app.log')
  #      handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
   #     handler.setFormatter(formatter)
  #      logger.addHandler(handler)
        log = []  # CBH
        logger.info('\n')
        logger.info('Calculation FL Building & Content Losses...')
        counter = 0
        try:
            # Measure script performance
            start_time = time.time()
            #print(f'\nStart time: {start_time}\n')
            #QC_Warning = self.QC_Warning.lower() == 'true'
        #    self.log_messages()
            self.change_directory()
            input = self.read_csv(self.UDFOrig)
            input_fields = self.get_field_names(input)
            # TODO: Check that input columns df has the required fields --> compare list(input.columns) to required_fields
            required_fields = ['UserDefinedFltyId', 'FltyId', 'OccupancyClass', 'Occ', 'Cost', 'Area', 'NumStories', 'FoundationType', 'FirstFloorHt', 'latitude', 'longitude', 'Latitude', 'Longitude']
        #    print(f'Input fields: {input_fields}\n')
        #    print(f'Required fields: {required_fields}')
            field_check = self.check_fields(input_fields, required_fields)
            # TODO: Rename input fields (to match required fields)
            print(f'\nAre all required fields provided? {field_check}\n')
            #if list(input.columns) == 
            self.set_output_fields()
            lookup_tables = ['Building_DDF_Riverine_LUT_Hazus4p0.csv', 'Building_DDF_CoastalA_LUT_Hazus4p0.csv', 'Building_DDF_CoastalV_LUT_Hazus4p0.csv', 'flBldgStructDmgFn.csv', 'Content_DDF_Riverine_LUT_Hazus4p0.csv', 'Content_DDF_CoastalA_LUT_Hazus4p0.csv', 'Content_DDF_CoastalV_LUT_Hazus4p0.csv', 'flBldgContDmgFn.csv', 'Inventory_DDF_LUT_Hazus4p0.csv', 'flBldgInvDmgFn.csv', 'flBldgEconParamSalesAndInv.csv', 'flDebris_LUT.csv', 'flRsFnGBS_LUT.csv']
            table_names = ['bddf_lut_riverine', 'bddf_lut_coastalA', 'bddf_lut_coastalV', 'bddf_lut_full', 'cddf_lut_riverine', 'cddf_lut_coastalA', 'cddf_lut_coastalV', 'cddf_lut_full', 'iddf_lut_riverine', 'iddf_lut_full', 'iecon_lut', 'debris_lut', 'rest_lut']
            lookup_tables_df_list = self.get_lookup_table(lookup_tables, table_names)
      #      for table in lookup_tables_df_list:
                #self.check_values(table)
                # self.check_optional_fields()
            aal_df_list = []
            for depth_grid in self.DepthGrids:
                raster_df = self.get_depth_grid(depth_grid)
               # self.set_value(raster_df, 'Depth_in_Struc' , -99999) #TODO: Review this
                #new_fields = ['Depth_Grid', 'Depth_in_Struc', 'flExp', 'SOID', 'BDDF_ID', 'BldgDmgPct', 'BldgLossUSD', 'ContentCostUSD', 'CDDF_ID', 'ContDmgPct', 'ContentLossUSD', 'InventoryCostUSD', 'IDDF_ID', 'InvDmgPct', 'InventoryLossUSD', 'DebrisID', 'Debris_Fin', 'Debris_Struc', 'Debris_Found', 'Debris_Tot', 'Restor_Days_Min', 'Restor_Days_Max', 'GridName']
                file_name = os.path.splitext(os.path.basename(depth_grid))[0]
                print(f'Calculating Standard Losses for {file_name} Depth Grid...')
                point_gdf = self.create_geo_df(input)
                #raster_new_fields = self.set_new_fields(raster_df)
                point_depths = self.spatial_join(point_gdf, raster_df)
                # self.null_check()
                point_depths = self.adjust_depths(point_depths)
                # self.check_coastal_zone()     --> "" if CoastalZoneCode is None else CoastalZoneCode
                # self.check_basement()         --> sosuf = 'B' if foundationType == 4 else 'N'
                # self.get_num_stories()        --> isn't this already done/provided?
                point_depths = self.create_specific_occ_id(point_depths)
                # TODO: Adjust all losts/costs for Coastal check
                # TODO: Add lookup check (for losses/costs) if input id's are missing (ie: inventory)
                point_depths = self.get_content_cost(point_depths)       #TODO: Review
                point_depths = self.get_inventory_cost(point_depths)     #TODO: Review
                point_depths = self.get_building_loss(point_depths)      #TODO: Review
                point_depths = self.get_content_loss(point_depths)       #TODO: Review
                point_depths = self.get_inventory_loss(point_depths)     #TODO: Review --> Adjust for > p24 & coastal zone?
                point_depths = self.get_debris(point_depths)
                point_depths = self.get_restore_time(point_depths)
                # Order column names
                column_names = ['FltyId', 'HNL_UDF_EQ', 'Occ', 'Cost', 'NumStories', 'FoundationType', 'FirstFloorHt', 'Area', 'ContentCost', 'BldgDamageFnID', 'CDDF_ID', 'YEARBUILT', 'Tract', 'Latitude', 'Longitude', 'Depth_Grid', 'Depth_in_Struc', 'flExp', 'SOID', 'ContentCostUSD', 'InventoryCostUSD', 'BldgDmgPct', 'BldgLossUSD', 'CDDF_ID', 'ContDmgPct', 'ContentLossUSD', 'IDDF_ID', 'InvDmgPct', 'InventoryLossUSD', 'DebrisID', 'Debris_Fin', 'Debris_Struc', 'Debris_Found', 'Debris_Tot', 'Restor_Days_Min', 'Restor_Days_Max', 'GridName']
                point_depths = point_depths.reindex(columns=column_names)
                output_file = os.path.splitext(os.path.basename(depth_grid))[0]
                # Sort values by Depth in Structure (descending)
                point_depths.sort_values(by=['Depth_in_Struc'], ascending=False, inplace=True)
                # For AAL: Add dataframe to list
                if (self.analysis_type and ('Average Annualized Loss (AAL)') in self.analysis_type and self.return_periods):
                    path = f'./UDF/output/aal/{output_file}-Standard.csv'
                    self.write_csv(point_depths, path)
                    point_depths.name = depth_grid
                    aal_df_list.append(point_depths)
                elif (self.analysis_type and ('Average Annualized Loss (AAL) with PELV') in self.analysis_type):
                    path = f'./UDF/output/pelv/{output_file}-PELV-100.csv'
                    self.write_csv(point_depths, path)
                    point_depths.name = '100'
                    aal_df_list.append(point_depths) # TODO: need to correctly catch this in order for AAL calculation - BC
                else:
                    path = f'./UDF/output/standard/{output_file}.csv'
                    self.write_csv(point_depths, path)
                   # print(f'Done with {output_file}.\n')
                    # return point_depths
############### PELV ######################
                # TODO: Pass these objects/functions to PELV class
                if (self.analysis_type and ('Average Annualized Loss (AAL) with PELV') in self.analysis_type):
                    UDFRoot = os.path.basename(self.UDFOrig)
                    y = os.path.split(depth_grid)[1]
                    x = UDFRoot.split('.')[0] + "_" + y.split('.')[0]
                    output_dir = os.path.join(self.ResultsDir, "for-demo", x + ".csv")
                    pelv = PELV.PELV(
                        point_depths, output_dir, self.flood_type, self.analysis_type
                    )

                    # Get Tracts
                    if ('Tract' in point_depths.columns) and pelv.check_for_hazus():
                        # Remove duplicate tract numbers (speeds up SQL query)
                        input_data_no_dupes = point_depths.drop_duplicates(
                            subset='Tract'
                        )
                        tract_list = tuple(
                            input_data_no_dupes['Tract'].apply(str).tolist()
                        )
                        tracts = pelv.get_tracts(tract_list)
                    else:
                        if ('Tract' in point_depths.columns):
                            print('Unable to find local install of HAZUS - will try Census REST API to map tracts')
                        else:
                            print('No tract column found - will try Census REST API to map tracts')
                        tracts = pelv.get_tracts_api(point_depths)
                    # Get PELV Curves
                    # TODO: Either install openpyxl with conda (add to environment.yaml) or convert to CSVs
                    if 'tract_state' and 'tract_county' in tracts.columns:
                        tracts.drop(
                            ['tract_state', 'tract_county'],
                            axis=1,
                            inplace=True,
                        )
                    print('\nLooking up PELV Curve values...')
                    pelv_curves = pelv.read_pelv_curves(self.flood_type)
                    pelv_curves_50 = pelv_curves[['tract', 50]]
                    # Join tables
                    if 'Tract' or 'tract' in tracts.columns:
                        if 'geometry' not in tracts.columns:
                            point_depths['Tract'] = point_depths['Tract'].apply(str)
                            input_udf_tracts_join = pd.merge(
                                point_depths,
                                tracts,
                                how="inner",
                                on=["Tract"],
                                suffixes=('', ''),
                            )
                        else:
                            input_udf_tracts_join = tracts
                    else:
                        input_udf_tracts_join = tracts
                    # Rename column
                    input_udf_tracts_join = input_udf_tracts_join.rename(
                        columns={'Tract': 'tract'}
                    )
                    pelv_curves_50['tract'] = pelv_curves_50['tract'].apply(str)
                    # Rename column
                    pelv_curves_50 = pelv_curves_50.rename(columns={50: 'PELV_50'})
                    pelv_curves_50_join = pd.merge(
                        input_udf_tracts_join,
                        pelv_curves_50,
                        how="inner",
                        on=["tract"],
                        suffixes=('', ''),
                    )
                    # Use PELV A values for both PELV A & PELV V --> replace values to match lookup table
                    if self.flood_type not in ('Riverine', 'CAE', 'Coastal A'):
                        pelv_curves_50_join['PELV_50'] = pelv_curves_50_join['PELV_50'].str.replace('V', 'A')
                    # Rename column back to original name
                    pelv_curves_50_join = pelv_curves_50_join.rename(
                        columns={'tract': 'Tract'}
                    )
                    # Replace '.' with '_' in column names
                    pelv_curves_50_join.columns = (
                        pelv_curves_50_join.columns.str.replace('[.]', '_')
                    )
                    if 'tract_geometry' in pelv_curves_50_join.columns:
                        pelv_curves_50_join.drop(
                            'tract_geometry',
                            axis=1,
                            inplace=True,
                        )
                    if 'crs' in pelv_curves_50_join.columns:
                        pelv_curves_50_join.drop(
                            'crs',
                            axis=1,
                            inplace=True,
                        )
                    if 'Tract_left' in pelv_curves_50_join.columns:
                        pelv_curves_50_join.drop(
                            'Tract_left',
                            axis=1,
                            inplace=True,
                        )
                    lookup_data = pd.read_excel(
                        r'./Lookuptables/AAL.xlsx', engine='openpyxl', header=1
                    )
                    lookup_data = lookup_data.iloc[:, :10]
                    # Re-order columns
                    lookup_data = lookup_data[['PELV_50', 50]]
                    pelv_value_merge = pd.merge(
                        pelv_curves_50_join,
                        lookup_data,
                        how="inner",
                        on=["PELV_50"],
                        suffixes=('', ''),
                    )
                    # TODO: Check if file(s) exists
                    # TODO: Handle points outside of tract boundary (ie: in ocean)
                    pelv_value_merge = pelv_value_merge.rename(
                        columns={50: 'PELV_Median', 'PELV_50': 'PELV_Median_Label'}
                    )
                    # TODO: Check if we want shapefile and/or geojson file(s) - BC
                    # Create GeoJSON file - currently disabled
                    #      to_geojson(pelv_value_merge, os.path.join(Resultsfgdb, 'output', file_name + ".geojson"))
                    # Create Shapefile - currently disabled
                    pelv_value_merge = pelv_value_merge.rename(
                        columns={
                            'PELV_Median': 'PELV',
                            'PELV_Median_Label': 'PELV_Label',
                        }
                    )
                    #        to_shapefile(pelv_value_merge, os.path.join(Resultsfgdb, 'output', file_name + ".shp"))
                    pelv_value_merge = pelv_value_merge.rename(
                        columns={
                            'PELV': 'PELV_Median',
                            'PELV_Label': 'PELV_Median_Label',
                        }
                    )
                    pelv_data_merged = pelv.get_pelv_depths(pelv_value_merge)
                    pelv_depths_id_list = ['10', '25', '50', '75', '200', '250', '500', '1000']
                    print('\nStarting PELV Curve analysis...\n')
                    for pelv_number in pelv_depths_id_list:
                        print(f'Calculating PELV for return period {pelv_number}...')
                        raster_df = self.get_depth_grid(depth_grid)
                        point_gdf = self.create_geo_df(input)
                        point_depths = self.spatial_join(point_gdf, raster_df)
                        pelv_col = pelv_data_merged[pelv_number]
                        pelv_median_col = pelv_data_merged['PELV_Median']
                        pelv_median_label_col = pelv_data_merged['PELV_Median_Label']
                        # Insert PELV labels & Values
                        point_depths.insert(1, pelv_number, pelv_median_col)
                        point_depths.insert(1, 'PELV_Median', pelv_col)
                        point_depths.insert(1, 'PELV_Median_Label', pelv_median_label_col)
                        pelv_depths  = self.adjust_depths(point_depths, pelv_depth=pelv_number)
                        pelv_depths = self.create_specific_occ_id(pelv_depths)
                        # TODO: Adjust all losts/costs for Coastal check
                        # TODO: Add lookup check (for losses/costs) if input id's are missing (ie: inventory)
                        pelv_depths = self.get_content_cost(pelv_depths)       #TODO: Review
                        pelv_depths = self.get_inventory_cost(pelv_depths)     #TODO: Review
                        pelv_depths = self.get_building_loss(pelv_depths)
                        pelv_depths = self.get_content_loss(pelv_depths)
                        pelv_depths = self.get_inventory_loss(pelv_depths)     #TODO: Review --> Adjust for > p24?
                        pelv_depths = self.get_debris(pelv_depths)
                        pelv_depths = self.get_restore_time(pelv_depths)
                        # Order column names
                        column_names = ['FltyId', 'HNL_UDF_EQ', 'Occ', 'Cost', 'NumStories', 'FoundationType', 'FirstFloorHt', 'Area', 'ContentCost', 'BldgDamageFnID', 'CDDF_ID', 'YEARBUILT', 'Tract', 'Latitude', 'Longitude', 'Depth_Grid', 'Depth_in_Struc', 'flExp', 'SOID', 'ContentCostUSD', 'InventoryCostUSD', 'BldgDmgPct', 'BldgLossUSD', 'CDDF_ID', 'ContDmgPct', 'ContentLossUSD', 'IDDF_ID', 'InvDmgPct', 'InventoryLossUSD', 'DebrisID', 'Debris_Fin', 'Debris_Struc', 'Debris_Found', 'Debris_Tot', 'Restor_Days_Min', 'Restor_Days_Max', 'GridName', 'PELV_Median_Label', 'PELV_Median']
                        pelv_depths = pelv_depths.reindex(columns=column_names)
                        output_file = os.path.splitext(os.path.basename(depth_grid))[0]
                        path = f'./UDF/output/pelv/{output_file}-PELV-{pelv_number}.csv'
                        # Sort values by Depth in Structure (descending)
                        pelv_depths.sort_values(by=['Depth_in_Struc'], ascending=False, inplace=True)
                        self.write_csv(pelv_depths, path)
                        pelv_depths.name = pelv_number
                        # Catch & store pelv dataframe for AAL calculations
                        aal_df_list.append(pelv_depths)
                        if pelv_number == '75':
                            # Move 100 year return period to the back of the list
                            aal_df_list += [aal_df_list.pop(0)]
                        #print(f'Done with {output_file}-PELV-{pelv_number}.\n')
                    UDFRoot = os.path.basename(self.UDFOrig)
                    y = os.path.split(depth_grid)[1]
                    x = UDFRoot.split('.')[0] + "_" + y.split('.')[0]
                    output_dir = os.path.join(self.ResultsDir, "pelv", x + ".csv")
                    return_periods_pelv_aal = ['10', '25', '50', '75', '100', '200', '250', '500', '1000']
                    output_path = './UDF/output/pelv/'
                    AAL.AAL(output_dir, return_periods_pelv_aal, aal_df_list, output_path, output_file)
############### END PELV ##################

############### AAL #######################
            if (self.analysis_type and ('Average Annualized Loss (AAL)') in self.analysis_type and self.return_periods):
                UDFRoot = os.path.basename(self.UDFOrig)
                y = os.path.split(depth_grid)[1]
                x = UDFRoot.split('.')[0] + "_" + y.split('.')[0]
                output_dir = os.path.join(self.ResultsDir, "aal", x + ".csv")
                output_path = './UDF/output/aal/'
                output_file = os.path.splitext(os.path.basename(depth_grid))[0]
                AAL.AAL(output_dir, self.return_periods, aal_df_list, output_path, output_file)
############### END AAL #######################
                # self.log_messages()
                # self.create_message()
                #print(f'\nPoint Depths Final Row Count:\n {len(point_depths.index)}')
            print('\nProcess completed successfully.')
            self.get_run_time(start_time)
        except Exception as e:
            print('\n')
            print(e)
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(fname)
            print(exc_type, exc_tb.tb_lineno)
            print('\n')

############### End AAL ##########################

    def get_loss_fn(self, row):
        try:
            l_index_column = row['l_index']
            u_index_column = row['u_index']
            fn = row[l_index_column] + (row['Depth_in_Struc'] - math.floor(row['Depth_in_Struc'])) * (row[u_index_column] - row[l_index_column] if row['Depth_in_Struc'] > 0 else 0) 
            return fn
        except:
            pass

    def get_building_loss(self, df):
        """Use lookup table to match BldgDamageFnID  --> "flBldgStructDmgFn.csv"
            Populates BldgDamage field

        Args:
            df ([type]): [description]
        """
        if 'BldgDamageFnID' in self.fmap:
            lookup_table = "flBldgStructDmgFn.csv"
        else:
            if self.flood_type == 'Riverine':
                lookup_table = "Building_DDF_Riverine_LUT_Hazus4p0.csv"
            elif self.flood_type in ('CAE', 'Coastal A'):
                lookup_table = "Building_DDF_CoastalA_LUT_Hazus4p0.csv"
            else:
                lookup_table = "Building_DDF_CoastalV_LUT_Hazus4p0.csv"
        lookup_table_df = self.get_lookup_table(lookup_table)
        if 'BldgDamageFnID' in self.fmap:
            df = df.merge(lookup_table_df, how='left', left_on='BldgDamageFnID', right_on='BldgDmgFnID')
        else:
            df = df.merge(lookup_table_df, how='left', left_on='SOID', right_on='SpecificOccupId')
        df['l_index'] = np.where(df['Depth_in_Struc'].apply(np.floor) < 0, 'm', 'p') + np.where(df['Depth_in_Struc'] > 24, '24', df['Depth_in_Struc'].abs().apply(np.floor).astype(str).apply(lambda x: x.replace('.0','')))
        df['u_index'] = np.where(df['Depth_in_Struc'].apply(np.ceil) < 0, 'm', 'p') + np.where(df['Depth_in_Struc'] > 24, '24', df['Depth_in_Struc'].abs().apply(np.ceil).astype(str).apply(lambda x: x.replace('.0','')))
        try:
            df['BldgDmgPct'] = df.apply(lambda row: self.get_loss_fn(row), axis=1)
            df['BldgLossUSD'] =  (df['BldgDmgPct'] / 100) * df['Cost']
            df['BldgLossUSD'] = df['BldgLossUSD'].astype(str).str.slice(0, 15).astype(float).round(2)
            if 'BldgDamageFnID' in self.fmap:
                remove_columns = ['BldgDmgFnID', 'Occupancy', 'Source', 'Description', 'm4', 'm3', 'm2','m1', 'p0', 'p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9', 'p10','p11', 'p12', 'p13', 'p14', 'p15', 'p16', 'p17', 'p18', 'p19', 'p20','p21', 'p22', 'p23', 'p24', 'Comment', 'l_index', 'u_index']
            else:
                df['BldgDamageFnID'] = df['DDF_ID']
                remove_columns = ['Occupancy', 'SpecificOccupId', 'Source', 'Description', 'Stories', 'Comment', 'm4', 'm3', 'm2', 'm1', 'p0', 'p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9', 'p10', 'p11', 'p12', 'p13', 'p14', 'p15', 'p16', 'p17', 'p18', 'p19', 'p20', 'p21', 'p22', 'p23', 'p24', 'DDF_ID', 'Basement', 'HazardRiverine', 'HazardCV', 'HazardCA', 'SortOrder', 'l_index', 'u_index']
            df = self.remove_columns(df, remove_columns)
            return df
        except:
            pass
        return df

    def get_content_loss(self, df):
        """Did user specify a Content DDF? If so, use that to reference the Full LUT, else use the Default LUT.
                CDDF_ID attribute, else none

        # Dictionary lookup: get damage percentage for the particular row at the particular depths
        # The Dictionary element comes from either the Full or the Default table; common code after this point.
        Args:
            df ([type]): [description]
        """
        if 'CDDF_ID' in self.fmap:
            lookup_table = "flBldgContDmgFn.csv"
        else:
            if self.flood_type == 'Riverine':
                lookup_table = "Content_DDF_Riverine_LUT_Hazus4p0.csv"
            elif self.flood_type in ('CAE', 'Coastal A'):
                lookup_table = "Content_DDF_CoastalA_LUT_Hazus4p0.csv"
            else:
                lookup_table = "Content_DDF_CoastalV_LUT_Hazus4p0.csv"
        lookup_table_df = self.get_lookup_table(lookup_table)
        if 'CDDF_ID' in self.fmap:
            df = df.merge(lookup_table_df, how='left', left_on='CDDF_ID', right_on='ContDmgFnId')
        else:
            df = df.merge(lookup_table_df, how='left', left_on='SOID', right_on='SpecificOccupId')
        df['l_index'] = np.where(df['Depth_in_Struc'].apply(np.floor) < 0, 'm', 'p') + np.where(df['Depth_in_Struc'] > 24, '24', df['Depth_in_Struc'].abs().apply(np.floor).astype(str).apply(lambda x: x.replace('.0','')))
        df['u_index'] = np.where(df['Depth_in_Struc'].apply(np.ceil) < 0, 'm', 'p') + np.where(df['Depth_in_Struc'] > 24, '24', df['Depth_in_Struc'].abs().apply(np.ceil).astype(str).apply(lambda x: x.replace('.0','')))
        try:
            df['ContDmgPct'] = df.apply(lambda row: self.get_loss_fn(row), axis=1)
            df['ContentLossUSD'] =  ((df['ContDmgPct'] / 100) * df['Cost']) / 2  #TODO: Review this
            df['ContentLossUSD'] = df['ContentLossUSD'].astype(str).str.slice(0, 15).astype(float).round(2)
            if 'CDDF_ID' in self.fmap:
                remove_columns = ['Occupancy', 'Source', 'Description', 'm4', 'm3', 'm2', 'm1', 'p0', 'p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9', 'p10', 'p11', 'p12', 'p13', 'p14', 'p15', 'p16', 'p17', 'p18', 'p19', 'p20', 'p21', 'p22', 'p23', 'p24', 'Comment', 'l_index', 'u_index']
            else:
                df['CDDF_ID'] = df['DDF_ID']
                remove_columns = ['Occupancy', 'SpecificOccupId', 'Source', 'Description', 'Stories', 'Comment', 'm4', 'm3', 'm2', 'm1', 'p0', 'p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9', 'p10', 'p11', 'p12', 'p13', 'p14', 'p15', 'p16', 'p17', 'p18', 'p19', 'p20', 'p21', 'p22', 'p23', 'p24', 'DDF_ID', 'Basement', 'HazardRiverine', 'HazardCV', 'HazardCA', 'SortOrder', 'l_index', 'u_index']
            df = self.remove_columns(df, remove_columns)
            return df
        except:
            pass

    def create_debris_id(self, occ, foundation_type, depth):
        if depth > 0:
            bsm = 'NB' # no basement (default)
            fnd = ('SG' if foundation_type in (4, 7) else 'FT')
            if occ in ('RES1', 'COM6') and foundation_type == 4:
                bsm = ('B' if occ == 'RES1' else 'NB')
                dsuf = ('-8' if depth < -4 else '-4' if depth < 0 else '0' if depth < 4 else '4' if depth < 6 else '6' if depth < 8 else '8')
            else:
                dsuf = ('0' if depth < 1 else '1' if depth < 4 else '4' if depth < 8 else '8' if depth < 12 else '12')
            debris_id = occ + bsm + fnd + dsuf
            return debris_id
        else:
            return ''

    def get_debris(self, df):
        """[summary]

        Args:
            df ([type]): [description]
        """
        lookup_table = 'flDebris_LUT.csv'
        lookup_table_df = self.get_lookup_table(lookup_table)
        df['DebrisID'] = [self.create_debris_id(occ, foundation_type, depth) for occ, foundation_type, depth in zip(df['Occ'], df['FoundationType'], df['Depth_Grid'])]
        df = df.merge(lookup_table_df, how='left', on='DebrisID')
        df['Debris_Fin'] = (df['Area'] * df['Finishes']) / 1000
        df['Debris_Found'] = (df['Area'] * df['Foundation']) / 1000
        df['Debris_Struc'] = (df['Area'] * df['Structure']) / 1000
        df['Debris_Tot'] = df['Debris_Fin'] + df['Debris_Found'] + df['Debris_Struc']
        df.fillna('', inplace=True)
        remove_columns = ['Description', 'Finishes', 'Structure','Foundation', 'Comment']
        df = self.remove_columns(df, remove_columns)
        return df

    def get_inventory_loss(self, df):
        """
        
        # Did user specify an Inventory DDF? If so, use that to reference the Full LUT, else use the Default LUT.
        # Due to Hazus-MH Flood conventions, the IDDF_ID is of type Text

        # Inventory Loss in US$: depends if user supplied an inventory cost field, and if it is > 0.
        # If not supplied, or 0, then use the default value based on OccupancyClass and Square Footage
        # per Hazus-MH Flood Technical Manual table
        # But note that the 'default value' is defined only for a subset of OccupancyClasses
        # Logic spelled out in accompanying spreadsheet - to simplify it, create three variables
        # OWDI = OccupancyClass with Default Inventory
        # USID = User-supplied Inventory DDF is supplied and legitimate
        # USIC = User-supplied Inventory Cost is supplied and non-zero and non-null


        Args:
            df ([type]): [description]
        """
        # lookup_table_id = 'Inventory_DDF_LUT_Hazus4p0.csv'
        # lookup_table_df = self.get_lookup_table(lookup_table_id)
        # lookup_table ="flBldgInvDmgFn.csv"
        # lookup_table_df = self.get_lookup_table(lookup_table)
        # lookup_df = lookup_table_df.merge(lookup_table_id, how='inner', left_on='InvDmgFnId', right_on='DDF_ID')

        # TODO Add if/else statement if IDDF is provided
        #lookup_table = 'Inventory_DDF_LUT.csv'
        try:
            lookup_table = 'Inventory_DDF_LUT.csv'
            lookup_table_df = self.get_lookup_table(lookup_table)
            econ_lookup_table = 'flBldgEconParamSalesAndInv.csv'
            econ_lookup_df = self.get_lookup_table(econ_lookup_table)
            lookup_df = lookup_table_df.merge(econ_lookup_df, how='inner', on='Occupancy')
            #lookup_table_df['Occupancy'] = lookup_table_df['Occupancy'].astype(str)
            #df['Occ'] = df['Occ'].astype(str)
            df = df.merge(lookup_df, how='left', left_on='Occ', right_on='Occupancy')
        except Exception as e:
            print('\n')
            print(e)
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(fname)
            print(exc_type, exc_tb.tb_lineno)
            print('\n')
        df.fillna(0, inplace=True)
        df['l_index'] = np.where(df['Depth_in_Struc'].apply(np.floor) < 0, 'm', 'p') + df['Depth_in_Struc'].abs().apply(np.floor).astype(str).apply(lambda x: x.replace('.0',''))
        df['u_index'] = np.where(df['Depth_in_Struc'].apply(np.ceil) < 0, 'm', 'p') + df['Depth_in_Struc'].abs().apply(np.ceil).astype(str).apply(lambda x: x.replace('.0',''))
        try:
            df['InvDmgPct'] = df.apply(lambda row: self.get_loss_fn(row), axis=1).round(2)
            df['InvCost'] = ((df['AnnualSalesPerSqFt'] * df['BusinessInvPctofSales'] * df['Area']) / 100).round(2)
            df['InventoryLossUSD'] =  ((df['InvDmgPct'] / 100) * df['InvCost']).round(2)
            df['IDDF_ID'] = df['DDF_ID'].astype(int)
            df.fillna(0, inplace=True)
            remove_columns = ['Occupancy', 'm4', 'm3', 'm2', 'm1', 'p0', 'p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9', 'p10', 'p11', 'p12', 'p13', 'p14', 'p15', 'p16', 'p17', 'p18', 'p19', 'p20', 'p21', 'p22', 'p23', 'p24', 'DDF_ID', 'HazardRiverine', 'HazardCV', 'HazardCA', 'AnnualSalesPerSqFt', 'BusinessInvPctofSales', 'OccupancyPlaceholder']
            df = self.remove_columns(df, remove_columns)
            return df
        except:
            pass

    def get_depth_grid(self, depth_grid):
        with rio.Env():
            with rio.open(depth_grid) as grid:
                crs = grid.crs
                is_utm = self.check_utm(grid)
                print(f'Is depth grid raster projection UTM? {is_utm}')
                image = grid.read(1) # first band
                results = (
                {'properties': {'Depth': v}, 'geometry': s}
                for i, (s, v) 
                in enumerate(
                    shapes(image, mask=None, transform=grid.transform))
                )
        geoms = list(results)
        polygon_raster = gpd.GeoDataFrame.from_features(geoms)
        polygon_raster = polygon_raster.set_crs(crs)
        polygon_raster.name = os.path.split(depth_grid)[1]
        return polygon_raster

    def get_content_multiplier(self, occ):
        Content_x_0p5 = [
            'RES1',
            'RES2',
            'RES3A',
            'RES3B',
            'RES3C',
            'RES3D',
            'RES3E',
            'RES3F',
            'RES4',
            'RES5',
            'RES6',
            'COM10',
        ]
        Content_x_1p0 = [
            'COM1',
            'COM2',
            'COM3',
            'COM4',
            'COM5',
            'COM8',
            'COM9',
            'IND6',
            'AGR1',
            'REL1',
            'GOV1',
            'EDU1',
        ]
        Content_x_1p5 = [
            'COM6',
            'COM7',
            'IND1',
            'IND2',
            'IND3',
            'IND4',
            'IND5',
            'GOV2',
            'EDU2',
        ]
        if occ in Content_x_0p5:
            cmult= 0.5
        elif occ in Content_x_1p0:
            cmult = 1.0
        elif occ in Content_x_1p5:
            cmult = 1.5
        else:
            cmult = 0
        return cmult

    def get_content_cost(self, df):
        """
        # Content and Inventory Cost. Determine each, even if structure not exposed to flooding
        # Content Loss in US$: depends if user supplied a content cost field, and if it is > 0.
        # If not, then use a default multiplier, depending on OccupancyClass, per Hazus-MH Flood Technical Manual table

        Args:
            df ([type]): [description]

        Returns:
            [type]: [description]
        """
        df['Mult'] = [self.get_content_multiplier(occ) for occ in df['Occ']]
        df['ContentCostUSD'] = df['Cost'] * df['Mult']
        df.drop(
            ['Mult'],
            axis=1,
            inplace=True,
        )
        return df

    def get_inventory_cost(self, df):
        # Default inventory DDF only defined for a subset. IF not in this set, set default Inventory Cost Basis = 0
        # Lookup table --> "flBldgEconParamSalesAndInv.csv"
        Inventory_List = [
            'COM1',
            'COM2',
            'IND1',
            'IND2',
            'IND3',
            'IND4',
            'IND5',
            'IND6',
            'AGR1',
        ]
        lookup_table = "flBldgEconParamSalesAndInv.csv"
        lookup_table_df = self.get_lookup_table(lookup_table)
        df = df.merge(lookup_table_df, how='left', left_on='Occ', right_on='Occupancy')
        df['InventoryCostUSD'] = [sales * pct_sales * area / 100 if occ in Inventory_List else 0 for sales, pct_sales, area, occ in zip(df['AnnualSalesPerSqFt'],  df['BusinessInvPctofSales'], df['Area'], df['Occ'])]
        df.drop(
            ['OccupancyPlaceholder', 'AnnualSalesPerSqFt', 'BusinessInvPctofSales', 'Occupancy'],
            axis=1,
            inplace=True,
        )
        # OWDI = OC in Inventory_List
        # xt = getValue(InvCost) if uicost else -1
        # # Clean up case where InvCost is supplied but is null
        # xt = xt if xt is not None else -1
        # if OWDI and xt == -1:
        #     # Use default cost formula
        #     for lutrow in iecon_lut:
        #         if lutrow['Occupancy'] == OC:
        #             GrossSales = lutrow['AnnualSalesPerSqFt']
        #             BusinessInv = lutrow['BusinessInvPctofSales']
        #             # Table imports as string type (?!) so we must convert tabular data to a float type
        #             # Yes, raw data is typically in Integer format, be flexible for future data which may be available in dollars.cents
        #             # Must divide by 100, as BusinessInv in the input table is a Percent figure
        #             # Area is in Square Feet
        #             icost = (
        #                 float(GrossSales)
        #                 * float(BusinessInv)
        #                 * area
        #                 / 100
        #             )
        #             break
        # # If a user-supplied Inventory Cost is supplied, use it.
        # elif xt > -1:
        #     icost = getValue(InvCost)
        # else:
        #     icost = 0
        return df

    def get_num_stories(self, input):
        pass
        """
                                    if OC[:4] == 'RES3':
                                    # RES3 has three categories: 1 3 5
                                somid = (
                                    '5'
                                    if numStories > 4
                                    else '3'
                                    if numStories > 2
                                    else '1'
                                )

                            elif OC[:4] == 'RES1':
                                # If NumStories is not an integer, assume Split Level residence
                                # Also, cap it at 3.
                                numStories = 3 if numStories > 3.0 else numStories
                                somid = (
                                    str(round(numStories))
                                    if numStories - round(numStories) == 0
                                    else 'S'
                                )

                            elif OC[:4] == 'RES2':
                                # Manuf. Housing is by definition limited to one story
                                somid = '1'

                            else:
                                # All other cases: Easy!  1-3, 4-7, 8+
                                somid = (
                                    'H'
                                    if numStories > 6
                                    else 'M'
                                    if numStories > 3
                                    else 'L'
                                )
        """

    # TODO: Refactor this to use a list of fields as input
    def get_lookup_table(self, tables, table_names=None):
        """
        Get lookup tables
        """
        #table_names = ['BRP', 'BCAP', 'BCVP', 'BFP', 'CRP', 'CCAP', 'CCVP', 'CFP', 'IRP', 'IFP', 'IEP', 'Debris', 'Rest']
        #table_names = ['bddf_lut_riverine', 'bddf_lut_coastalA', 'bddf_lut_coastalV', 'bddf_lut_full', 'cddf_lut_riverine', 'cddf_lut_coastalA', 'cddf_lut_coastalV', 'cddf_lut_full', 'iddf_lut_riverine', 'iddf_lut_full', 'iecon_lut', 'debris_lut', 'rest_lut']
        if table_names:
            lookup_tables = zip(tables, table_names)
            lookup_df_list = []
            for table in lookup_tables:
                table_location = os.path.join(self.LUT_Dir, table[0])
                data = pd.read_csv(table_location)
                data.name = table[1]
                lookup_df_list.append(data)
            return lookup_df_list
        else:
            table_location = os.path.join(self.LUT_Dir, tables)
            lookup_df = self.read_csv(table_location)
            lookup_df = pd.read_csv(table_location)
            return lookup_df

    def remove_columns(self, df, columns):
        df.drop(
            columns,
            axis=1,
            inplace=True,
        )
        return df

    def create_restore_id(self, occ, depth):
        if depth > 0:
            dsuf = ('0' if depth < 0 else '1' if depth < 1 else '4' if depth < 4 else '8' if depth < 8 else '12' if depth < 12 else '24')
            restore_id = occ + dsuf
            return restore_id
        else:
            return ''

    def get_restore_time(self, df):
        """[summary]
        # Restoration Time Calculation - the basis for all Direct Economic Loss numbers
        # Based on the Min and Max days listed in   [dbo].[flRsFnGBS]
        # Note how the table differs slightly from the TM, esp with Res with basements
        # Note that the TM suggests some of these are not subject to a 10% threshold
        # The method suggests using the Maximum; for completeness, the script produces both.
        ###########################################################
        # Calculate only for exposed buildings.
        Args:
            df ([type]): [description]

        Returns:
            [type]: [description]
        """
        try:
            lookup_table = 'flRsFnGBS_LUT.csv'
            lookup_table_df = self.get_lookup_table(lookup_table)
            df['RestFnID'] = [self.create_restore_id(occ, depth) for occ, depth in zip(df['Occ'], df['Depth_Grid'])]
            df = df.merge(lookup_table_df, how='left', on='RestFnID')
            df['Restor_Days_Min'] = np.where(df['Depth_Grid'] > 0, df['Min_Restor_Days'].astype(str).apply(lambda x: x.replace('.0','')), 0)
            df['Restor_Days_Max'] = np.where(df['Depth_Grid'] > 0, df['Max_Restor_Days'].astype(str).apply(lambda x: x.replace('.0','')), 0)
            df.fillna('', inplace=True)
            remove_columns = ['l_index', 'u_index','RestFnID', 'Occupancy', 'Min_Depth', 'Max_Depth','Min_Restor_Days', 'Max_Restor_Days']
            df = self.remove_columns(df, remove_columns)
            return df
        except:
            pass

    def read_csv(self, file):
        input = pd.read_csv(file)
        # input_list = []
        # for file in file_list:
            # data = pd.read_csv(f'./UDF/for-demo/{file}.csv')
            # data.name = file[0]
            # input_list.append(data)
        #return input_list
        return input

    def set_new_fields(self, input, new_fields):
        # BldgDmgPct = "BldgDmgPct"
        # BldgLossUSD = "BldgLossUSD"
        # ContentCostUSD = "ContentCostUSD"
        # ContDmgPct = "ContDmgPct"
        # ContentLossUSD = "ContentLossUSD"
        # InventoryCostUSD = "InventoryCostUSD"
        # InvDmgPct = "InvDmgPct"
        # InventoryLossUSD = "InventoryLossUSD"

        # Note there are no Hazus equivalents for the following output attributes.
        # DOGAMI believes these to be value-added, and suggests Hazus provide this information.
        # See spreadsheet accompanying the script for naming convention
        # flExp = "flExp"
        # Depth_in_Struc = "Depth_in_Struc"
        # # The renamed raster sample data. "RASTERVALU" is not a useful name
        # Depth_Grid = "Depth_Grid"
        # SOID = "SOID" if SOI == '' else SOI  # Specific Occupancy ID
        # BDDF_ID = "BDDF_ID" if BldgDamageFnID == '' else BldgDamageFnID
        # CDDF_ID = "CDDF_ID" if ContDamageFnId == '' else ContDamageFnId
        # IDDF_ID = "IDDF_ID" if InvDamageFnId == '' else InvDamageFnId
        # DebrisID = "DebrisID"
        # Debris_Fin = "Debris_Fin"  # Debris for Finish work
        # Debris_Struc = "Debris_Struc"  # Debris from structural elements
        # Debris_Found = "Debris_Found"  # Debris from foundation
        # Debris_Tot = "Debris_Tot"  # Total Debris - sum of the previous
        # GridName = "GridName"
        # Restor_Days_Min = "Restor_Days_Min"  # Repair/Restoration times
        # Restor_Days_Max = "Restor_Days_Max"
      #  field_names = field_names + new_fields
        input_new_fields = pd.concat([input, pd.DataFrame(columns=new_fields)]).fillna('')
        return input_new_fields

    def set_output_fields(self):
        #fields = ['BldgDmgPct', 'BldgLossUSD', 'ContentCostUSD', 'ContDmgPct', 'ContentLossUSD', 'InventoryCostUSD', 'InvDmgPct', 'InventoryLossUSD', 'flExp', 'Depth_in_Struc', 'Depth_Grid', 'SOID' , 'BDDF_ID', 'CDDF_ID', 'IDDF_ID' , 'DebrisID', 'Debris_Fin' , 'Debris_Struc' , 'Debris_Found' , 'Debris_Tot' , 'GridName', 'Restor_Days_Min', 'Restor_Days_Max']
        fields = ['BldgDmgPct', 'BldgLossUSD', 'ContentCostUSD', 'ContDmgPct', 'ContentLossUSD', 'InventoryCostUSD', 'InvDmgPct', 'InventoryLossUSD', 'flExp', 'SOID' , 'BDDF_ID', 'CDDF_ID', 'IDDF_ID' , 'DebrisID', 'Debris_Fin' , 'Debris_Struc' , 'Debris_Found' , 'Debris_Tot' , 'GridName', 'Restor_Days_Min', 'Restor_Days_Max']

    def set_value(self, raster_df, name, value):
        raster_df[name] = value # if None or ''

    def spatial_join(self, points, raster):
        # Reproject points df to match raster projection
        points = points.to_crs(raster.crs.to_dict())
        points_in_raster = gpd.sjoin(points, raster, how='left')
        points_in_raster['GridName'] = raster.name
        return points_in_raster

    def write_csv(self, df, path):
        path = path
        line_terminator='\n'
        df.to_csv(path, index=False, line_terminator=line_terminator)

    def get_run_time(self, start_time):
        end_time = time.time()
        run_time = (end_time - start_time) / 60
        if run_time > 1:
            print(f'Total processing time: {int(round(run_time, 0))} minutes.\n')
        elif run_time < 1:
            print(f'Total processing time: {int(round(run_time * 60, 0))} seconds.\n')
        else:
            print(f'Total processing time: {int(round(run_time, 0))} minute.\n')

"""
# ----JIRA 916 Notes----
# TODO: Create list of tracts that do not intersect a tract
# TODO: Query Census REST API for nearest Tract neighbor (if no intersect)


def read_csv(csv):
    data = pd.read_csv(csv)
    crs = {'init': 'epsg:4326'}
    geometry = [Point(xy) for xy in zip(data["Longitude"], data["Latitude"])]
    geodata = gpd.GeoDataFrame(data, crs=crs, geometry=geometry)
    return geodata

"""
# TODO: Create shapefile
# TODO: Create GeoJSON file
# TODO: Refactor PELV analysis (change to subclass of UDF)
# TODO: Add comments to methods
# TODO: Handle no tract column for PELV analysis (to use ESRI REST API)