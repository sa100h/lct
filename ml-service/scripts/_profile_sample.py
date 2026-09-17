"""Inspect alarm rows in the 2026 sample journal."""
import pandas as pd

J = "/home/junai/lct/ml-data/журнал_событий_пример.csv"
S = "/home/junai/lct/ml-data/справочник_каналов_датчиков.csv"

j = pd.read_csv(J, dtype={"значение_датчика": "string"})
sen = pd.read_csv(S)
tt = j[j["тревожение" if "тревожение" in j.columns else "тревожное"] == True]
print("alarm rows:", len(tt))
print("value counts among alarms:")
print(tt["значение_датчика"].value_counts().head(25))
m = tt.merge(sen, on="ид_канала_данных", how="left")
print("\nalarm sensor types:")
print(m.groupby(["тип_инж_системы", "тип_датчика"]).size().sort_values(ascending=False).head(20))
print("\nsample alarm rows:")
print(m.head(20).to_string())

# how often 'тревожное' is true for these channels in non-alarm rows?
print("\nnon-alarm values sample:")
na = j[j["тревожное"] == False]
print(na["значение_датчика"].value_counts().head(15))
