import geopandas as gpd
import json
import os
import pandas as pd
import pyodbc as py
import requests
import subprocess
import sys
import time
import warnings

# Disable pandas warnings
warnings.filterwarnings('ignore')


class PELV():
    def __init__(self, input_data, output_dir, flood_type, analysis_type):
        self.input_data = input_data
        self.output_dir = output_dir
        self.flood_type = flood_type
        self.analysis_type = analysis_type

    def createConnection(self, orm='pyodbc'):
        try:
            drivers = [
                '{ODBC Driver 17 for SQL Server}',
                '{ODBC Driver 13.1 for SQL Server}',
                '{ODBC Driver 13 for SQL Server}',
                '{ODBC Driver 11 for SQL Server} ',
                '{SQL Server Native Client 11.0}',
                '{SQL Server Native Client 10.0}',
                '{SQL Native Client}',
                '{SQL Server}'
            ]
            computer_name = os.environ['COMPUTERNAME']
            if orm == 'pyodbc':
                # create connection with the latest driver
                for driver in drivers:
                    try:
                        conn = py.connect(self.getConnectionString(
                            'pyodbc').format(d=driver, cn=computer_name))
                        break
                    except:
                        conn = py.connect(self.getConnectionString(
                            'pyodbc_auth').format(d=driver, cn=computer_name))
                        break
            return conn
        except Exception as e:
            print(e)

    def getConnectionString(self, stringName):
        try:
            with open("./src/connectionStrings.json") as f:
                connectionStrings = json.load(f)
                connectionString = connectionStrings[stringName]
            return connectionString
        except Exception as e:
            print(e)

    # User must have HAZUS installed
    def get_tracts(self, tract_list):
        sql = f"SELECT Tract, Shape.STAsText() AS tract_geometry, Shape.STSrid as crs FROM [syHazus].[dbo].[syTract] WHERE Tract IN {tract_list}"
        try:
            tracts_df = self.query(sql)
            return tracts_df
        except Exception as e:
            print(e)

    def query(self, sql):
        try:
            conn = self.createConnection()
            df = pd.read_sql(sql, conn)
            return df
        except Exception as e:
            print(e)

    # # TODO: Convert lookup tables to CSV files (instead of Excel)
    def read_pelv_curves(self, flood_type):
        if flood_type in ('Riverine', 'CAE', 'Coastal A'):
            sheet_name = 'PELV A'
        else:
            sheet_name = 'PELV V'
        data = pd.read_excel(r'./Lookuptables/BCS-Flood-PELV-Curves-50-DC.xlsx',
                             sheet_name=sheet_name, engine='openpyxl')
        return data

    def to_csv(self, df, path, line_terminator=None, drop_geom=False):
        """ Exports a StudyRegionDataFrame to an Esri Shapefile

            Keyword Arguments: \n
                path: str -- the output directory path, file name, and extention (example: 'C:/directory/filename.shp')
        """
        try:
            if drop_geom and 'geometry' in df.columns:
                df.drop(
                    'geometry',
                    axis=1,
                    inplace=True,
                )
            df.to_csv(path, index=False, line_terminator=line_terminator)
        except Exception as e:
            print(e)

    def to_geojson(self, df, path):
        """ Exports a StudyRegionDataFrame to an Esri Shapefile

            Keyword Arguments: \n
                path: str -- the output directory path, file name, and extention (example: 'C:/directory/filename.shp')
        """
        try:
            # TODO: Add check that input data is only POINT data
            # if 'geometry' not in df.columns:
            #     self = addGeometry()
            crs = {'init': 'epsg:4326'}
            gdf = gpd.GeoDataFrame(df, geometry='geometry', crs=crs)
            gdf.to_file(path, driver='GeoJSON')
        except Exception as e:
            print(e)

    def to_shapefile(self, df, path):
        """ Exports a StudyRegionDataFrame to an Esri Shapefile

            Keyword Arguments: \n
                path: str -- the output directory path, file name, and extention (example: 'C:/directory/filename.shp')
        """
        try:
            # TODO: Add check that input data is only POINT data
            # if 'geometry' not in df.columns:
            #     self = addGeometry()
            crs = {'init': 'epsg:4326'}
            gdf = gpd.GeoDataFrame(df, geometry='geometry', crs=crs)
            gdf.to_file(path, driver='ESRI Shapefile')
            # TODO: Check is this is needed
            # Separate by geometry type
            # points_gdf = gdf[gdf['geometry'].geom_type == 'Point']
            # if not points_gdf.empty:
            #     points_path = path.replace('.shp', '_points.shp')
            #     points_gdf.to_file(points_path, driver='ESRI Shapefile')
            # # Create lines shapefile
            # lines_gdf = gdf[gdf['geometry'].geom_type == 'LineString']
            # if not lines_gdf.empty:
            #     lines_path = path.replace('.shp', '_lines.shp')
            #     lines_gdf.to_file(lines_path, driver='ESRI Shapefile')
        except Exception as e:
            print(e)

    # Get tract (from ESRI REST API)
    def get_tracts_api(self, points):
        try:
            if 'Tract' in points.columns:
                points_no_dupes = points.drop_duplicates(subset='Tract')
                points_no_dupes['tract_state'] = points_no_dupes['Tract'].astype(
                    str).str[:2]
                points_no_dupes['tract_county'] = points_no_dupes['Tract'].astype(
                    str).str[2:5]
                tract_state = ''.join(
                    points_no_dupes['tract_state'].astype(str).unique().tolist())
                tract_counties = ','.join(
                    points_no_dupes['tract_county'].astype(str).unique().tolist())
                tracts_url = f'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2010/MapServer/14/query?where=STATE%3D{tract_state}+AND+COUNTY+IN+%28{tract_counties}%29&text=&objectIds=&time=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&distance=&units=esriSRUnit_Foot&relationParam=&outFields=STATE%2CCOUNTY%2CTRACT&returnGeometry=true&returnTrueCurves=false&maxAllowableOffset=&geometryPrecision=&outSR=&havingClause=&returnIdsOnly=false&returnCountOnly=false&orderByFields=&groupByFieldsForStatistics=&outStatistics=&returnZ=false&returnM=false&gdbVersion=&historicMoment=&returnDistinctValues=false&resultOffset=&resultRecordCount=&returnExtentOnly=false&datumTransformation=&parameterValues=&rangeValues=&quantizationParameters=&featureEncoding=esriDefault&f=geojson'
                for attempt in range(3):
                    try:
                        tracts_response = requests.get(tracts_url, timeout=120)
                    except:
                        time.sleep(20)
                        continue
                    else:
                        break
                if tracts_response:
                    tracts = tracts_response.json().get('features')
                    tracts = gpd.GeoDataFrame.from_features(tracts)
                else:
                    print('Unable to get tracts')
            else:
                print('Could not find tract field. Process may take longer')
                # Get first point (for initial reference)
                first_point = points.iloc[0]
                x, y = first_point['Longitude'], first_point['Latitude']
                url = f'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2010/MapServer/14/query?where=1%3D1&text=&objectIds=&time=&geometry={x}%2C{y}&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelWithin&distance=&units=esriSRUnit_Foot&relationParam=&outFields=STATE%2CCOUNTY%2CTRACT&returnGeometry=false&returnTrueCurves=false&maxAllowableOffset=&geometryPrecision=&outSR=&havingClause=&returnIdsOnly=false&returnCountOnly=false&orderByFields=&groupByFieldsForStatistics=&outStatistics=&returnZ=false&returnM=false&gdbVersion=&historicMoment=&returnDistinctValues=false&resultOffset=&resultRecordCount=&returnExtentOnly=false&datumTransformation=&parameterValues=&rangeValues=&quantizationParameters=&featureEncoding=esriDefault&f=geojson'
                for attempt in range(3):
                    try:
                        initial_response = requests.get(url, timeout=30)
                    except:
                        time.sleep(10)
                        continue
                    else:
                        break
                data = initial_response.json().get('features')[0].get('properties')
                state = data.get('STATE')
                tracts_url = f'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2010/MapServer/14/query?where=STATE%3D{state}&text=&objectIds=&time=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&distance=&units=esriSRUnit_Foot&relationParam=&outFields=STATE%2CCOUNTY%2CTRACT&returnGeometry=true&returnTrueCurves=false&maxAllowableOffset=&geometryPrecision=&outSR=4326&havingClause=&returnIdsOnly=false&returnCountOnly=false&orderByFields=&groupByFieldsForStatistics=&outStatistics=&returnZ=false&returnM=false&gdbVersion=&historicMoment=&returnDistinctValues=false&resultOffset=&resultRecordCount=&returnExtentOnly=false&datumTransformation=&parameterValues=&rangeValues=&quantizationParameters=&featureEncoding=esriDefault&f=geojson'
                for attempt in range(3):
                    try:
                        tracts_response = requests.get(tracts_url, timeout=120)
                    except:
                        time.sleep(10)
                        continue
                    else:
                        break
                tracts = tracts_response.json().get('features')
                tracts = gpd.GeoDataFrame.from_features(tracts)
            cols = ['STATE', 'COUNTY', 'TRACT']
            tracts['Tracts'] = tracts['STATE'].astype(
                str) + tracts['COUNTY'].astype(str) + tracts['TRACT'].astype(str)
            tracts.drop(columns=cols, axis=1, inplace=True)
            new_column_names = {
                'Tracts': 'Tract'
            }
            tracts = tracts.rename(columns=new_column_names)
            points_in_tracts = self.intersect_tracts(points, tracts)
            return points_in_tracts
        except Exception as e:
            print('\n')
            print(e)
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(fname)
            print(exc_type, exc_tb.tb_lineno)
            print('\n')

    def intersect_tracts(self, points, tracts):
        points_in_tracts = gpd.sjoin(points, tracts)
        points_in_tracts = points_in_tracts.rename(
            columns={'Tract_right': 'Tract'})
        points_in_tracts.drop('index_right', axis=1, inplace=True)
        return points_in_tracts

    def check_for_hazus(self):
        try:
            proc = subprocess.Popen(
                'osql -L', shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            out, err = proc.communicate()
            if 'HAZUS' in str(out):
                return True
            else:
                return False
        except Exception as e:
            print(e)
            return False

    def get_nearest_tract(self, tracts):
        pass

    def get_pelv_depths(self, data):
        # Reference AAL spreadsheet - skip first row
        lookup_data = pd.read_excel(
            r'./Lookuptables/AAL.xlsx', engine='openpyxl', header=1)

        lookup_data = lookup_data.iloc[:, :10]
        # Re-order columns
        lookup_data = lookup_data[['PELV_50',
                                   10, 25, 50, 75, 200, 250, 500, 1000]]
        new_column_names = {
            10: '10',
            25: '25',
            50: '50',
            75: '75',
            200: '200',
            250: '250',
            500: '500',
            1000: '1000'
        }
        # Rename columns
        lookup_data = lookup_data.rename(columns=new_column_names)
        # Join tables
        # TODO: Adjust PELV_50 name (to/from PELV_Median_Label)
        data_merged = pd.merge(data, lookup_data, how="inner", left_on='PELV_Median_Label', right_on="PELV_50")
        return data_merged



    # ----JIRA 916 Notes----
    # TODO: Create list of tracts that do not intersect a tract
    # TODO: Query Census REST API for nearest Tract neighbor (if no intersect)
