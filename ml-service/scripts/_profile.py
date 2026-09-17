"""Quick profile of the sample journal + reference tables."""
import pandas as pd

J = "/home/junai/lct/ml-data/журнал_событий_пример.csv"
S = "/home/junai/lct/ml-data/справочник_каналов_датчиков.csv"
O = "/home/junai/lct/ml-data/справочник_объектов_диспетчер.csv"

j = pd.read_csv(J)
print("journal:", j.shape)
print(j.dtypes)
print("тревожное:", j["тревожное"].value_counts().to_dict())
print("date range:", j["дата"].min(), j["дата"].max())
print("unique channels:", j["ид_канала_данных"].nunique())
print("head:")
print(j.head(3).to_string())
print("\nvalue_датчика sample stats:")
print(j["значение_датчика"].describe())

s = pd.read_csv(S)
print("\nsensors ref:", s.shape)
print(s["тип_инж_системы"].value_counts().to_dict())
print("typ датчика:")
print(s["тип_датчика"].value_counts().to_dict())

o = pd.read_csv(O)
print("\nobjects ref:", o.shape)
print(o["вид_объекта"].value_counts().to_dict())
print(o.head(8).to_string())
