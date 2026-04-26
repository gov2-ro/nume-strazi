"""Starter seed for curated tables.
Tiny on purpose — enough to demonstrate joins, not to be authoritative.
Real curation comes later (CSV import, Wikidata, or LLM-assisted)."""
import sqlite3, argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--db", default="data/streets.db")
con = sqlite3.connect(_ap.parse_args().db)

# ---- Persons (small, hand-picked, names already seen in sample) ----
PERSONS = [
    # core_name_norm,             full,                      gender, b,    d,    era,         profession,    nat
    ("mihai eminescu",            "Mihai Eminescu",          "M", 1850, 1889, "premodern", "poet",         "RO"),
    ("ion creanga",               "Ion Creangă",             "M", 1837, 1889, "premodern", "writer",       "RO"),
    ("nichita stanescu",          "Nichita Stănescu",        "M", 1933, 1983, "communist", "poet",         "RO"),
    ("george cosbuc",             "George Coșbuc",           "M", 1866, 1918, "premodern", "poet",         "RO"),
    ("vasile alecsandri",         "Vasile Alecsandri",       "M", 1821, 1890, "1848",      "writer",       "RO"),
    ("ioan slavici",              "Ioan Slavici",            "M", 1848, 1925, "premodern", "writer",       "RO"),
    ("nicolae balcescu",          "Nicolae Bălcescu",        "M", 1819, 1852, "1848",      "revolutionary","RO"),
    ("avram iancu",               "Avram Iancu",             "M", 1824, 1872, "1848",      "revolutionary","RO"),
    ("tudor vladimirescu",        "Tudor Vladimirescu",      "M", 1780, 1821, "premodern", "revolutionary","RO"),
    ("mihai viteazul",            "Mihai Viteazul",          "M", 1558, 1601, "medieval",  "voievod",      "RO"),
    ("matei basarab",             "Matei Basarab",           "M", 1588, 1654, "medieval",  "voievod",      "RO"),
    ("nicolae iorga",             "Nicolae Iorga",           "M", 1871, 1940, "interwar",  "historian",    "RO"),
    ("octavian goga",             "Octavian Goga",           "M", 1881, 1938, "interwar",  "poet",         "RO"),
    ("simion barnutiu",           "Simion Bărnuțiu",         "M", 1808, 1864, "1848",      "revolutionary","RO"),
    ("george toparceanu",          "George Topârceanu",       "M", 1886, 1937, "interwar",  "poet",         "RO"),
    ("lucian blaga",              "Lucian Blaga",            "M", 1895, 1961, "interwar",  "philosopher",  "RO"),
    ("george bacovia",            "George Bacovia",          "M", 1881, 1957, "interwar",  "poet",         "RO"),
    ("petre ispirescu",           "Petre Ispirescu",         "M", 1830, 1887, "premodern", "writer",       "RO"),
    ("axente sever",              "Axente Sever",            "M", 1821, 1906, "1848",      "revolutionary","RO"),
    ("anghel saligny",            "Anghel Saligny",          "M", 1854, 1925, "premodern", "engineer",     "RO"),
    ("camil ressu",               "Camil Ressu",             "M", 1880, 1962, "interwar",  "painter",      "RO"),
    ("costache negruzzi",         "Costache Negruzzi",       "M", 1808, 1868, "1848",      "writer",       "RO"),
    ("elena vacarescu",           "Elena Văcărescu",         "F", 1864, 1947, "premodern", "writer",       "RO"),
    ("maria",                      "Regina Maria",            "F", 1875, 1938, "interwar",  "royalty",      "RO"),
    ("elisabeta",                  "Regina Elisabeta",        "F", 1843, 1916, "premodern", "royalty",      "RO"),
    ("carol i",                    "Regele Carol I",          "M", 1839, 1914, "premodern", "royalty",      "RO"),
    ("ferdinand",                  "Regele Ferdinand",        "M", 1865, 1927, "interwar",  "royalty",      "RO"),
    ("victor babes",              "Victor Babeș",            "M", 1854, 1926, "premodern", "scientist",    "RO"),
    ("carol davila",              "Carol Davila",            "M", 1828, 1884, "premodern", "scientist",    "RO"),
    ("c.i. parhon",               "C.I. Parhon",             "M", 1874, 1969, "communist", "scientist",    "RO"),
    ("mina minovici",             "Mina Minovici",           "M", 1858, 1933, "premodern", "scientist",    "RO"),
    ("n.d. paulescu",             "N.D. Paulescu",           "M", 1869, 1931, "interwar",  "scientist",    "RO"),
    ("alexandru averescu",        "Alexandru Averescu",      "M", 1859, 1938, "interwar",  "military",     "RO"),
    ("traian mosoiu",             "Traian Moșoiu",           "M", 1868, 1932, "interwar",  "military",     "RO"),
    ("titel petrescu",            "Titel Petrescu",          "M", 1888, 1957, "interwar",  "politician",   "RO"),
    ("pintea",                     "Pintea Haiducul",         "M", 1670, 1703, "medieval",  "outlaw",       "RO"),
]
con.executemany("""INSERT OR IGNORE INTO persons
    (core_name_norm,full_name,gender,birth_year,death_year,era,profession,nationality)
    VALUES (?,?,?,?,?,?,?,?)""", PERSONS)

# ---- Nature terms (Romanian street favorites) ----
NATURE = [
    # core_name_norm, term, type
    ("florilor","Florilor","flower"),("trandafirilor","Trandafirilor","flower"),
    ("rozelor","Rozelor","flower"),("crinului","Crinului","flower"),
    ("lalelelor","Lalelelor","flower"),("liliacului","Liliacului","flower"),
    ("salcamilor","Salcâmilor","tree"),("salcamului","Salcâmului","tree"),
    ("nucilor","Nucilor","tree"),("nucului","Nucului","tree"),
    ("plopilor","Plopilor","tree"),("plopului","Plopului","tree"),
    ("salciei","Salciei","tree"),("stejarului","Stejarului","tree"),
    ("teiului","Teiului","tree"),("bradului","Bradului","tree"),
    ("merilor","Merilor","tree"),("visinilor","Vișinilor","tree"),
    ("alunilor","Alunilor","tree"),("macesului","Măceșului","tree"),
    ("padurii","Pădurii","forest"),("campului","Câmpului","field"),
    ("luncii","Luncii","meadow"),("dealului","Dealului","hill"),
    ("vaii","Văii","valley"),("muntelui","Muntelui","mountain"),
    ("soarelui","Soarelui","weather"),("primaverii","Primăverii","season"),
    ("ciocarliei","Ciocârliei","bird"),("mierlei","Mierlei","bird"),
    ("randunelelor","Rândunelelor","bird"),("vrabiei","Vrabiei","bird"),
    ("lupului","Lupului","animal"),("ursului","Ursului","animal"),
    ("cerbului","Cerbului","animal"),
]
con.executemany("INSERT OR IGNORE INTO nature_terms VALUES (?,?,?,NULL)", NATURE)

# ---- Religious / abstract category seed (non-person, non-nature) ----
CATEGORIES = [
    ("scolii","institutional","school",None),
    ("bisericii","religious","church",None),
    ("morii","trade","mill",None),
    ("stadionului","institutional","stadium",None),
    ("garii","institutional","train_station",None),
    ("primariei","institutional","city_hall",None),
    ("principala","abstract","main",None),
    ("libertatii","ideological","freedom",None),
    ("unirii","ideological","unification",None),
    ("republicii","ideological","republic",None),
    ("independentei","ideological","independence",None),
    ("victoriei","ideological","victory",None),
    ("pacii","ideological","peace",None),
    ("revolutiei","ideological","revolution",None),
    ("eroilor","commemorative","heroes",None),
]
con.executemany("INSERT OR IGNORE INTO name_categories VALUES (?,?,?,?)", CATEGORIES)

# ---- Place references seen in sample ----
PLACES = [
    ("careiului","Carei","ro_city","RO",None),
    ("maramuresului","Maramureș","ro_region","RO",None),
    ("bucovinei","Bucovina","ro_region","RO",None),
    ("dorna","Dorna","ro_region","RO",None),
    ("toplita","Toplița","ro_city","RO",None),
    ("romana","Roma","foreign_city","IT",None),
]
con.executemany("INSERT OR IGNORE INTO place_refs VALUES (?,?,?,?,?)", PLACES)

con.commit()
print("Seeded:")
for t in ("persons","nature_terms","name_categories","place_refs"):
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {n}")
