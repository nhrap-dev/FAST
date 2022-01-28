import pandas as pd
import warnings

# Disable pandas warnings
warnings.filterwarnings('ignore')

class AAL():
    def __init__(self, output_dir, return_periods, aal_df_list, output_path, output_file):
        self.output_dir = output_dir
        self.return_periods = [int(rp) for rp in return_periods]
        self.aal_df_list = aal_df_list
        self.output_path = output_path
        self.output_file  = output_file
        self.df_list = []
        self.set_aal_items()
        self.export_sum()

    def get_aal(self, item, rp, recalc_fields, previous_item=None, previous_rp=None, next_item=None, next_rp=None):
        """The AAL is calculated for each structure using the formula:
                AAL = Ln*(1/n-1/(n+1))/2+Ln*(1/(n-1)-1/(n+1))/2+....+Ln*(1/(n-1)-1/(n+1))/2+Ln*(1/(n-1)-1/(n))/2
                where n is the return period frequency
                Ex: If return periods 10, 25, 50 and 100 are provided the formula will be:
                AAL = L10*(1/10-1/25)/2 + L25*(1/10-1/50)/2 + L50*(1/25-1/100)/2 + L100*(1/50-1/100)/2
                * L = Loss field
                * n = return period frequency

        Args:
            item (dataframe): Pandas dataframe
            rp (str): Return period
            recalc_fields (list): Fields to re-calculate
            previous_item (dataframe, optional): Previous return period dataframe. Defaults to None.
            previous_rp (str, optional): Previous return period. Defaults to None.
            next_item (dataframe, optional): Next return period dataframe.. Defaults to None.
            next_rp (str, optional): Next return period. Defaults to None.

        Returns:
            None
        """
        print(f'Calculating AAL for return period {rp}...')
        try:
            aal_fields = []
            for column in recalc_fields:
                # Create column for AAL value
                new_column_name = f'{column}_aal'
                aal_fields.append(new_column_name)
                # First RP
                if previous_rp is None and next_rp is not None:
                    fn = lambda row: (((1 / rp) - (1 / next_rp)) / 2) * row[column]
                # Next/Second RP
                elif previous_rp is not None and next_rp is not None:
                    fn = lambda row: (((1 / previous_rp) - (1 / next_rp))) / 2 * row[column]
                # Last RP
                elif previous_rp is not None and next_rp is None:
                    fn = lambda row: (((1 / previous_rp) - (1 / rp))) / 2 * row[column]
                # Apply function to data frame rows
                item[new_column_name] = item.apply(fn, axis=1)
            # Remove/filter rows that have all 0's for losses
            item = pd.concat([item.loc[item[recalc_fields[column]] > 0] for column in range(len(recalc_fields))]).drop_duplicates()
            keep_columns_list = [
                'FltyId',
                'Occ',
                'Cost',
                'ContentCost',
                'InventoryLossUSD_aal',
                'BldgLossUSD_aal',
                'ContentLossUSD_aal',
                'Latitude',
                'Longitude'
            ]
            item = item[keep_columns_list]
            columns_to_string_list = [
                'FltyId',
                'Cost',
                'ContentCost',
                'Latitude',
                'Longitude',
            ]
            item[columns_to_string_list] = item[columns_to_string_list].fillna('').astype(str)
            item.name = rp
            self.df_list.append(item)
            self.export_df(item, rp)
        except Exception as e:
            print(e)
    
    def export_df(self, item, rp):
        """Export return period dataframe to CSV

        Args:
            item (dataframe): Pandas dataframe
            rp (str): Return period
        """
        path = f'{self.output_path}{self.output_file}-{rp}-AAL.csv'
        line_terminator='\n'
        item.to_csv(path, index=False, line_terminator=line_terminator)

    def export_sum(self):
        """Export aggregated (sum) of all losses to CSV
        """
        group_columns_list = [
            'FltyId',
            'Occ',
            'Cost',
            'ContentCost',
            'Latitude',
            'Longitude'
        ]
        df_final = pd.concat(self.df_list).groupby(group_columns_list).sum(numeric_only=True).reset_index().drop_duplicates()
        sum_columns = [
                'InventoryLossUSD_aal',
                'BldgLossUSD_aal',
                'ContentLossUSD_aal'
        ]
        df_final['TotalLossUSD_aal'] = df_final[sum_columns].sum(axis=1)
        df_final['BldgLossRatio'] = (df_final['BldgLossUSD_aal'] + df_final['ContentLossUSD_aal']) / (df_final['Cost'].astype(float) + df_final['ContentCost'].astype(float))
        df_final['BldgLossRatioPct'] = df_final['BldgLossRatio'] * 100
        df_final.fillna(0, inplace=True)
        # Sort columns
        df_final = df_final.sort_index(axis=1)
        df_final.sort_values(by=['FltyId'], inplace=True)
        # Re-order columns
        column_order_list = [
            'FltyId',
            'Occ',
            'Cost',
            'ContentCost',
            'BldgLossUSD_aal',
            'ContentLossUSD_aal',
            'InventoryLossUSD_aal',
            'TotalLossUSD_aal',
            'BldgLossRatio',
            'BldgLossRatioPct',
            'Latitude',
            'Longitude',
        ]
        df_final = df_final[column_order_list]
        path = f'{self.output_path}{self.output_file}-AAL-Sum.csv'
        line_terminator='\n'
        df_final.to_csv(path, index=False, line_terminator=line_terminator)

    def set_aal_items(self):
        """Set all AAL items & iterate return periods for AAL calculations
        """
        recalc_fields = [
            'BldgLossUSD',
            'ContentLossUSD',
            'InventoryLossUSD',
        ]
        for index, rp in enumerate(self.return_periods):
            rp = rp
            item = self.aal_df_list[index]
            # First RP
            if index == 0:
                next_rp = self.return_periods[index + 1]
                next_item = self.aal_df_list[index + 1]
                self.get_aal(item, rp, recalc_fields, next_item=next_item, next_rp=next_rp)
            # Second/Next RP
            elif index > 0 and index < (len(self.return_periods) - 1):
                previous_rp = self.return_periods[index - 1]
                previous_item = self.aal_df_list[index - 1]
                next_rp = self.return_periods[index + 1]
                next_item = self.aal_df_list[index + 1]
                self.get_aal(item, rp, recalc_fields, previous_item=previous_item, previous_rp=previous_rp, next_item=next_item, next_rp=next_rp)
            # Last RP
            else:
                previous_rp = self.return_periods[index - 1]
                previous_item = self.aal_df_list[index - 1]
                self.get_aal(item, rp, recalc_fields, previous_item=previous_item, previous_rp=previous_rp)