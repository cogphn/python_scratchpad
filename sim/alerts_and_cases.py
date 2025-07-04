import pandas as pd
import sdv 
import pugsql 

from sdv.metadata import Metadata
import random

# modified version of "https://gist.github.com/alcheng10/9b3aab9c1fe3f3bc805a176a28fde859"
import holidays

def create_dim_date(start_date, end_date):
    '''
    Create Dimension Date in Pandas

    :return df_date : DataFrame
    '''
    from pandas.tseries.offsets import MonthEnd, QuarterEnd

    # Construct DIM Date Dataframe
    df_date = pd.DataFrame({"Date": pd.date_range(start=f'{start_date}', end=f'{end_date}', freq='D')})

    def get_end_of_month(pd_date):
        if pd_date.is_month_end == True:
            return pd_date
        else:
            return pd_date + MonthEnd(1)

    def get_end_of_quarter(pd_date):
        if pd_date.is_quarter_end == True:
            return pd_date
        else:
            return pd_date + QuarterEnd(1)

    # Add in attributes
    df_date["Day"] = df_date.Date.dt.day_name()
    df_date["Week"] = df_date.Date.dt.isocalendar().week
    df_date["Month"] = df_date.Date.dt.month
    df_date["Quarter"] = df_date.Date.dt.quarter
    df_date["Year"] = df_date.Date.dt.year
    # df_date["Fiscal_Year"] = df_date['Date'].dt.to_period('A-JUN')
    df_date['EndOfMonth'] = df_date['Date'].apply(get_end_of_month)
    df_date['EOM_YN'] = df_date['Date'].dt.is_month_end
    df_date['EndOfQuarter'] = df_date['Date'].apply(get_end_of_quarter)
    df_date['EOQ_YN'] = df_date['Date'].dt.is_quarter_end

    return df_date

def create_dim_date_with_workday(start_date, end_date):
    '''
    Creates a dimension date that has workday_YN column.

    Uses Australia NSW public holidays.

    :return df_date : DataFrame
    '''

    df_date = create_dim_date(start_date, end_date)

    # Start with default that it is workday
    df_date['Workday_YN'] = True

    # Exclude public holidays in NSW
    for index, row in df_date.iterrows():
        if row['Day'] in ['Saturday', 'Sunday']:
            df_date.loc[index, 'Workday_YN'] = False
        date = row['Date'].strftime("%Y-%m-%d")
        if date in holidays.Australia(prov='NSW'):
            df_date.loc[index, 'Workday_YN'] = False

    return df_date
  #


dim_date = create_dim_date('2025-01-01', '2025-12-31')



# Sample Data
sample_data = {

  'tables': [
    {
      'name': 'alerts', 'data':
        [
          { 'id':1, 'creation_ts':'2025-05-01T00:03:13', 'case_id': None, 'status': 'open', 'closed_ts': None },
          { 'id':2, 'creation_ts':'2025-05-01T00:02:13', 'case_id': 100, 'status': 'open', 'closed_ts': None },
          { 'id':3, 'creation_ts':'2025-06-01T12:03:13', 'case_id': 100, 'status': 'open', 'closed_ts': None },
          { 'id':4, 'creation_ts':'2025-06-01T13:00:13', 'case_id': 101, 'status': 'open', 'closed_ts': '2025-06-05T22:11:12' },
          { 'id':8, 'creation_ts':'2025-06-01T13:00:14', 'case_id': 101, 'status': 'open', 'closed_ts': '2025-06-05T22:11:12' },
          { 'id':9, 'creation_ts':'2025-06-01T13:00:16', 'case_id': 101, 'status': 'open', 'closed_ts': '2025-06-05T22:11:12' },
          { 'id':5, 'creation_ts':'2025-07-03T14:00:13', 'case_id': None, 'status': 'closed', 'closed_ts': '2025-07-05T14:00:13' },
          { 'id':6, 'creation_ts':'2025-07-05T14:00:13', 'case_id': None, 'status': 'closed', 'closed_ts': '2025-07-05T18:00:13' },
        ]
    },
    {
      'name': 'cases', 'data':
        [
          { 'id': 100, 'creation_ts':'2025-05-03T04:03:11', 'status':'open', 'closed_ts': None },
          { 'id': 101, 'creation_ts':'2025-06-02T04:03:11', 'status':'closed', 'closed_ts': '2025-06-05T22:11:12' },
        ]
    }
  ]
}

alerts = pd.DataFrame(sample_data['tables'][0]['data'])
cases = pd.DataFrame(sample_data['tables'][1]['data'])

alerts['creation_ts'] = pd.to_datetime(alerts['creation_ts'])
alerts['acknowledged'] = alerts['creation_ts'] + pd.Timedelta(hours=random.randint(0,3), minutes=random.randint(1,50))

# setup
real_data = {
    'alerts': alerts,
    'cases': cases
}
metadata = Metadata.detect_from_dataframes(data=real_data)

metadata.add_relationship(
    parent_table_name='cases',
    child_table_name='alerts',
    parent_primary_key='id',
    child_foreign_key='case_id'
)

metadata.validate()
# metadata.visualize(show_table_details='full')

# generate data 
from sdv.multi_table import HMASynthesizer

synthesizer = HMASynthesizer(metadata)
synthesizer.fit(real_data)
new_data = synthesizer.sample(scale=20)

alerts_synth = new_data['alerts']
cases_synth = new_data['cases']


# a little cleanup, and adding of date dimension fields 

alerts_synth['period'] = pd.to_datetime(alerts_synth['creation_ts']).dt.to_period('M')
alerts_synth['created_date'] = alerts_synth['creation_ts'].dt.date
cases_synth['period'] = pd.to_datetime(cases_synth['creation_ts']).dt.to_period('M')
cases_synth['period'] = pd.to_datetime(cases_synth['creation_ts']).dt.date

alerts_synth['year'] = pd.to_datetime(alerts_synth['creation_ts']).dt.to_period('Y')
cases_synth['year'] = pd.to_datetime(alerts_synth['creation_ts']).dt.to_period('Y')

cases_synth.loc[cases_synth['closed_ts'].isna(), 'status'] = 'open'
cases_synth.loc[~cases_synth['closed_ts'].isna(), 'status'] = 'closed'




if __name__ == '__main__':
    print('[*] starting...')
    alerts_synth.to_csv("alerts_synth.csv", index=False)
    cases_synth.to_csv("cases_synth.csv", index=False)
    dim_date.to_csv("dim_date.csv", index=False)

    print('[.] Done')
#
