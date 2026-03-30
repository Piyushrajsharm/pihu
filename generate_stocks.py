import pandas as pd
import numpy as np

# Generate dummy stock data for 40 Indian tech stocks
stocks = [
    "TCS", "INFY", "RELIANCE", "HDFCBANK", "ICICIBANK", "WIPRO", "HCLTECH", "TECHM", 
    "BHARTIARTL", "SBIN", "BAJFINANCE", "ASIANPAINT", "MARUTI", "TITAN", "ULTRACEMCO", 
    "SUNPHARMA", "NESTLEIND", "JSWSTEEL", "TATASTEEL", "ADANIENT", "ADANIPORTS", 
    "HINDALCO", "GRASIM", "ONGC", "NTPC", "POWERGRID", "COALINDIA", "ITC", "HINDUNILVR", 
    "BRITANNIA", "CIPLA", "DRREDDY", "DIVISLAB", "APOLLOHOSP", "EICHERMOT", "M&M", 
    "HEROMOTOCO", "BAJAJ-AUTO", "LT", "BPCL"
]

data = []
for symbol in stocks:
    for day in range(30):
        data.append({
            "Symbol": symbol,
            "Date": pd.Timestamp.now() - pd.Timedelta(days=day),
            "Price": np.random.uniform(500, 5000),
            "Volume": np.random.randint(1000, 1000000),
            "Change %": np.random.uniform(-5, 5)
        })

df = pd.DataFrame(data)
df.to_csv("d:/JarvisProject/pihu/stocks_df.csv", index=False)
print("Generated d:/JarvisProject/pihu/stocks_df.csv")
