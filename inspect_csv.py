import pandas as pd
import os

df = pd.read_csv("stocks_df.csv", nrows=5)
print("Columns:", df.columns.tolist())
print("---")
print("Dtypes:")
print(df.dtypes)
print("---")
print("Sample:")
print(df.head(3).to_string())
print("---")
print(f"File size: {os.path.getsize('stocks_df.csv')/1024/1024:.1f} MB")
