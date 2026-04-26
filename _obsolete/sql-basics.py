import sqlite3 
import pandas as pd 
# import pprint
from icecream import ic


# Create your connection. 
cnx = sqlite3.connect('../../data/nume-strazi/strazi-ro.db') 

query = 'SELECT Artera, COUNT(Artera) as Counter from RSV_AEP_21 GROUP by Artera ORDER by Counter DESC limit 100'
query = 'SELECT SUBSTR(Artera, 0, 7) AS prefix, COUNT(*) AS Counter from RSV_AEP_21 GROUP BY SUBSTR(Artera, 0, 7) ORDER BY Counter DESC'
query = 'SELECT * from RSV_AEP_21 limit 100'
df = pd.read_sql_query(query, cnx)

ic('--start')
u = df['Artera'].str.partition()
# secondlast = pd.DataFrame({'First': u[0], 'Last': u[2].str.split().str[-1]})

secondlast = pd.DataFrame({'First': u[2], 'Last': u[2].str.split().str[-1]})
# secondlast = pd.DataFrame({'First': u[0], 'First1': u[1], 'First2': u[2]})

# hhead = df.head(10)
ic(secondlast)
ic('--done')

# pp = pprint.PrettyPrinter(indent=4)
# pp.pprint(df)
# ic(df)
# print(df)
