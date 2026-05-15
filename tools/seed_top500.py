"""Pre-classify the top-500 unclassified core_name_norm values.

Generates data/curation/classified_top500.csv then imports it.
Run after build_db.py + seed_lookups.py.

Usage:
  python3 tools/seed_top500.py
  python3 tools/seed_top500.py --dry-run
"""
import csv, sys
from pathlib import Path

OUT = Path("data/curation/classified_top500.csv")

# ── NATURE TERMS ────────────────────────────────────────────────────────────
# (core_name_norm, term_display, nature_type)
NATURE = [
    # trees
    ("teilor",          "Teilor",        "tree"),
    ("alunului",        "Alunului",      "tree"),
    ("frasinului",      "Frasinului",    "tree"),
    ("mesteacanului",   "Mesteacănului", "tree"),
    ("fagului",         "Fagului",       "tree"),
    ("pinului",         "Pinului",       "tree"),
    ("socului",         "Socului",       "tree"),
    ("artarului",       "Arțarului",     "tree"),
    ("gorunului",       "Gorunului",     "tree"),
    ("malinului",       "Mălinului",     "tree"),
    ("paltinului",      "Paltinului",    "tree"),
    ("molidului",       "Molidului",     "tree"),
    ("arinului",        "Arinului",      "tree"),
    ("ulmului",         "Ulmului",       "tree"),
    ("visinului",       "Vișinului",     "tree"),
    ("dudului",         "Dudului",       "tree"),
    ("duzilor",         "Duzilor",       "tree"),
    ("caisului",        "Caisului",      "tree"),
    ("prunului",        "Prunului",      "tree"),
    ("prunilor",        "Prunilor",      "tree"),
    ("salciilor",       "Salciilor",     "tree"),
    ("carpenului",      "Carpenului",    "tree"),
    ("gutuiului",       "Gutuiului",     "tree"),
    ("gutuilor",        "Gutuilor",      "tree"),
    ("ficusului",       "Ficusului",     "tree"),
    ("castanului",      "Castanului",    "tree"),
    ("stejarilor",      "Stejarilor",    "tree"),
    ("arinilor",        "Arinilor",      "tree"),
    ("pinilor",         "Pinilor",       "tree"),
    ("caisilor",        "Caișilor",      "tree"),
    ("piersicului",     "Piersicului",   "tree"),
    ("piersicilor",     "Piersicilor",   "tree"),
    ("perilor",         "Perilor",       "tree"),
    ("parului",         "Parului",       "tree"),
    ("cornului",        "Cornului",      "tree"),
    ("catinei",         "Cătinei",       "tree"),
    ("dafinului",       "Dafinului",     "tree"),
    ("cetinei",         "Cetinei",       "tree"),
    ("rachitei",        "Răchitei",      "tree"),
    ("platanului",      "Platanului",    "tree"),
    ("ciresilor",       "Cireșilor",     "tree"),
    ("pomilor",         "Pomilor",       "tree"),
    ("brazilor",        "Brazilor",      "tree"),
    ("livezilor",       "Livezilor",     "orchard"),
    ("livezii",         "Livezii",       "orchard"),
    ("livezi",          "Livezi",        "orchard"),
    # forest/grove
    ("crangului",       "Crângului",     "forest"),
    ("codrului",        "Codrului",      "forest"),
    ("dumbravei",       "Dumbravei",     "forest"),
    ("dumbrava",        "Dumbrava",      "forest"),
    ("fagetului",       "Făgetului",     "forest"),
    ("alunis",          "Aluniș",        "forest"),
    ("alunisului",      "Alunișului",    "forest"),
    # flowers
    ("narciselor",      "Narciselor",    "flower"),
    ("bujorului",       "Bujorului",     "flower"),
    ("crizantemelor",   "Crizantemelor", "flower"),
    ("magnoliei",       "Magnoliei",     "flower"),
    ("viorelelor",      "Viorelelor",    "flower"),
    ("zambilelor",      "Zambilelor",    "flower"),
    ("ghioceilor",      "Ghioceilor",    "flower"),
    ("iasomiei",        "Iasomiei",      "flower"),
    ("garofitei",       "Garofiței",     "flower"),
    ("margaretelor",    "Margaretelor",  "flower"),
    ("crizantemei",     "Crizantemei",   "flower"),
    ("nufarului",       "Nufărului",     "flower"),
    ("orhideelor",      "Orhideelor",    "flower"),
    ("violetelor",      "Violetelor",    "flower"),
    ("zambilei",        "Zambilei",      "flower"),
    ("branduselor",     "Brândușelor",   "flower"),
    ("nuferilor",       "Nuferilor",     "flower"),
    ("panselutelor",    "Panseluțelor",  "flower"),
    ("panselelor",      "Panselelor",    "flower"),
    ("daliei",          "Daliei",        "flower"),
    ("brandusei",       "Brândușei",     "flower"),
    ("gladiolelor",     "Gladiolelor",   "flower"),
    ("lacramioarelor",  "Lăcrămioarelor","flower"),
    ("zorelelor",       "Zorelelor",     "flower"),
    ("garoafelor",      "Garoafelor",    "flower"),
    ("garoafei",        "Garoafei",      "flower"),
    ("albastrelelor",   "Albăstrelelor", "flower"),
    ("micsunelelor",    "Micșunelelor",  "flower"),
    ("lalelei",         "Lalelei",       "flower"),
    ("toporasilor",     "Toporașilor",   "flower"),
    ("romanitei",       "Romaniței",     "flower"),
    ("sanzienelor",     "Sânzienelor",   "flower"),
    ("lavandei",        "Lavandei",      "flower"),
    ("macului",         "Macului",       "flower"),
    ("macilor",         "Macilor",       "flower"),
    ("irisului",        "Irisului",      "flower"),
    ("narcisei",        "Narcisei",      "flower"),
    ("craitelor",       "Craițelor",     "flower"),
    ("margaritarului",  "Mărgaritarului","flower"),
    ("freziei",         "Freziei",       "flower"),
    ("muscatelor",      "Mușcatelor",    "flower"),
    ("petuniei",        "Petuniei",      "flower"),
    ("petuniilor",      "Petuniilor",    "flower"),
    ("panselutei",      "Panseluței",    "flower"),
    ("begoniei",        "Begoniei",      "flower"),
    ("anemonelor",      "Anemonelor",    "flower"),
    ("orhideei",        "Orhideei",      "flower"),
    ("gladiolei",       "Gladiolei",     "flower"),
    ("lacramioarei",    "Lăcrămioarei",  "flower"),
    ("tuberozelor",     "Tuberozelor",   "flower"),
    ("lotusului",       "Lotusului",     "flower"),
    ("cameliei",        "Cameliei",      "flower"),
    ("hortensiei",      "Hortensiei",    "flower"),
    ("margaretei",      "Margaretei",    "flower"),
    ("toporasi",        "Toporași",      "flower"),
    ("sulfinei",        "Sulfinei",      "flower"),
    ("cicoarei",        "Cicoarei",      "flower"),
    # plants
    ("pelinului",       "Pelinului",     "plant"),
    ("busuiocului",     "Busuiocului",   "plant"),
    ("trifoiului",      "Trifoiului",    "plant"),
    ("inului",          "Inului",        "plant"),
    ("rozmarinului",    "Rozmarinului",  "plant"),
    ("musetelului",     "Mușețelului",   "plant"),
    ("papadiei",        "Păpădiei",      "plant"),
    ("nalbei",          "Nalbei",        "plant"),
    ("spicului",        "Spicului",      "plant"),
    ("graului",         "Grâului",       "plant"),
    ("viilor",          "Viilor",        "plant"),
    # fruits
    ("capsunilor",      "Căpșunilor",    "fruit"),
    ("zmeurei",         "Zmeurei",       "fruit"),
    ("murelor",         "Murelor",       "fruit"),
    ("fragilor",        "Fragilor",      "fruit"),
    ("afinului",        "Afinului",      "fruit"),
    # birds
    ("randunicii",      "Rândunicii",    "bird"),
    ("berzei",          "Berzei",        "bird"),
    ("cucului",         "Cucului",       "bird"),
    ("soimului",        "Șoimului",      "bird"),
    ("privighetorii",   "Privighetorii", "bird"),
    ("privighetorilor", "Privighetorilor","bird"),
    ("cocorilor",       "Cocorilor",     "bird"),
    ("corbului",        "Corbului",      "bird"),
    ("lebedei",         "Lebedei",       "bird"),
    ("cocorului",       "Cocorului",     "bird"),
    ("pescarusului",    "Pescărușului",  "bird"),
    ("berzelor",        "Berzelor",      "bird"),
    ("egretei",         "Egretei",       "bird"),
    ("porumbeilor",     "Porumbeilor",   "bird"),
    ("vulturului",      "Vulturului",    "bird"),
    ("vulturilor",      "Vulturilor",    "bird"),
    # animals
    ("caprioarei",      "Căprioarei",    "animal"),
    ("zimbrului",       "Zimbrului",     "animal"),
    ("albinelor",       "Albinelor",     "animal"),
    ("albinei",         "Albinei",       "animal"),
    ("stupilor",        "Stupilor",      "animal"),
    # water
    ("izvorului",       "Izvorului",     "water"),
    ("lacului",         "Lacului",       "water"),
    ("izvoarelor",      "Izvoarelor",    "water"),
    ("izvor",           "Izvor",         "water"),
    ("raului",          "Râului",        "water"),
    ("garlei",          "Gârlei",        "water"),
    ("iazului",         "Iazului",       "water"),
    ("paraului",        "Pârâului",      "water"),
    ("fantanii",        "Fântânii",      "water"),
    ("fantanilor",      "Fântânilor",    "water"),
    ("cismelei",        "Cișmelei",      "water"),
    ("baltii",          "Bâlții",        "water"),
    ("prundului",       "Prundului",     "water"),
    ("malului",         "Malului",       "water"),
    ("vadului",         "Vadului",       "water"),
    # meadow / pasture
    ("pajistei",        "Pajiștei",      "meadow"),
    ("pasunii",         "Pășunii",       "meadow"),
    ("poienii",         "Poienii",       "meadow"),
    ("poienitei",       "Poieniței",     "meadow"),
    ("poiana",          "Poiana",        "meadow"),
    ("izlazului",       "Izlazului",     "meadow"),
    ("islazului",       "Islazului",     "meadow"),
    ("imasului",        "Imasului",      "meadow"),
    ("pajistei",        "Pajiștei",      "meadow"),
    # geography / terrain
    ("colinei",         "Colinei",       "hill"),
    ("magura",          "Măgura",        "hill"),
    ("magurii",         "Măgurii",       "hill"),
    ("magurei",         "Măgurei",       "hill"),
    ("piscului",        "Piscului",      "peak"),
    ("plaiului",        "Plaiului",      "geography"),
    ("sesului",         "Șesului",       "geography"),
    # seasons / sky / weather
    ("zorilor",         "Zorilor",       "sky"),
    ("toamnei",         "Toamnei",       "season"),
    ("verii",           "Verii",         "season"),
    ("rasaritului",     "Răsăritului",   "sky"),
    ("apusului",        "Apusului",      "sky"),
    ("amurgului",       "Amurgului",     "sky"),
    ("curcubeului",     "Curcubeului",   "weather"),
    ("azurului",        "Azurului",      "sky"),
    ("zefirului",       "Zefirului",     "weather"),
    ("vantului",        "Vântului",      "weather"),
    ("crivatului",      "Crivățului",    "weather"),
    ("luceafarului",    "Luceafărului",  "sky"),
    ("stelelor",        "Stelelor",      "sky"),
    ("lunii",           "Lunii",         "sky"),
    ("aurora",          "Aurora",        "sky"),
]

# ── PERSONS ─────────────────────────────────────────────────────────────────
# (core_name_norm, full_name, gender, birth, death, era, profession, nat, qid)
PERSONS = [
    ("stefan cel mare",      "Ștefan cel Mare",              "M", 1433, 1504, "medieval",  "voievod",     "RO", "Q44700"),
    ("decebal",              "Decebal",                      "M", None,  106, "ancient",   "king",        "RO", "Q37180"),
    ("crisan",               "Crișan",                       "M", 1730, 1785, "premodern", "revolutionary","RO", None),
    ("aurel vlaicu",         "Aurel Vlaicu",                 "M", 1882, 1913, "premodern", "engineer",    "RO", "Q46740"),
    ("traian",               "Împăratul Traian",             "M",   53,  117, "ancient",   "emperor",     None, "Q1425"),
    ("mihail kogalniceanu",  "Mihail Kogălniceanu",          "M", 1817, 1891, "1848",      "politician",  "RO", "Q333229"),
    ("closca",               "Cloșca",                       "M", 1748, 1785, "premodern", "revolutionary","RO", None),
    ("gheorghe doja",        "Gheorghe Doja",                "M", 1470, 1514, "medieval",  "revolutionary","RO", "Q153418"),
    ("mihail sadoveanu",     "Mihail Sadoveanu",             "M", 1880, 1961, "interwar",  "writer",      "RO", "Q217048"),
    ("george enescu",        "George Enescu",                "M", 1881, 1955, "interwar",  "composer",    "RO", "Q188215"),
    ("alexandru ioan cuza",  "Alexandru Ioan Cuza",          "M", 1820, 1873, "premodern", "politician",  "RO", "Q208518"),
    ("cuza voda",            "Alexandru Ioan Cuza",          "M", 1820, 1873, "premodern", "politician",  "RO", "Q208518"),
    ("dimitrie cantemir",    "Dimitrie Cantemir",            "M", 1673, 1723, "premodern", "politician",  "RO", "Q192043"),
    ("vlad tepes",           "Vlad Țepeș",                   "M", 1428, 1477, "medieval",  "voievod",     "RO", "Q44611"),
    ("ion luca caragiale",   "Ion Luca Caragiale",           "M", 1852, 1912, "premodern", "writer",      "RO", "Q217022"),
    ("i. l. caragiale",      "Ion Luca Caragiale",           "M", 1852, 1912, "premodern", "writer",      "RO", "Q217022"),
    ("mihail eminescu",      "Mihai Eminescu",               "M", 1850, 1889, "premodern", "poet",        "RO", "Q169930"),
    ("mihai viteazu",        "Mihai Viteazul",               "M", 1558, 1601, "medieval",  "voievod",     "RO", "Q156605"),
    ("constantin brancoveanu","Constantin Brâncoveanu",      "M", 1654, 1714, "premodern", "voievod",     "RO", "Q216023"),
    ("liviu rebreanu",       "Liviu Rebreanu",               "M", 1885, 1944, "interwar",  "writer",      "RO", "Q217046"),
    ("mircea cel batran",    "Mircea cel Bătrân",            "M", 1355, 1418, "medieval",  "voievod",     "RO", "Q208494"),
    ("nicolae titulescu",    "Nicolae Titulescu",            "M", 1882, 1941, "interwar",  "diplomat",    "RO", "Q366104"),
    ("horia",                "Horia",                        "M", 1730, 1785, "premodern", "revolutionary","RO", None),
    ("petru rares",          "Petru Rareș",                  "M", 1483, 1546, "medieval",  "voievod",     "RO", "Q312528"),
    ("ciprian porumbescu",   "Ciprian Porumbescu",           "M", 1853, 1883, "premodern", "composer",    "RO", "Q381100"),
    ("ana ipatescu",         "Ana Ipătescu",                 "F", 1805, 1875, "1848",      "revolutionary","RO", None),
    ("traian vuia",          "Traian Vuia",                  "M", 1872, 1950, "premodern", "engineer",    "RO", "Q1354864"),
    ("tudor arghezi",        "Tudor Arghezi",                "M", 1880, 1967, "interwar",  "poet",        "RO", "Q331003"),
    ("ecaterina teodoroiu",  "Ecaterina Teodoroiu",          "F", 1894, 1917, "premodern", "military",    "RO", "Q1298714"),
    ("alexandru vlahuta",    "Alexandru Vlahuță",            "M", 1858, 1919, "premodern", "writer",      "RO", None),
    ("anton pann",           "Anton Pann",                   "M", 1796, 1854, "premodern", "writer",      "RO", "Q696820"),
    ("vasile lupu",          "Vasile Lupu",                  "M", 1595, 1661, "medieval",  "voievod",     "RO", "Q524987"),
    ("alexandru cel bun",    "Alexandru cel Bun",            "M", 1375, 1432, "medieval",  "voievod",     "RO", "Q312534"),
    ("dragos voda",          "Dragoș Vodă",                  "M", None, 1354, "medieval",  "voievod",     "RO", None),
    ("andrei muresanu",      "Andrei Mureșanu",              "M", 1816, 1863, "1848",      "poet",        "RO", "Q647392"),
    ("iuliu maniu",          "Iuliu Maniu",                  "M", 1873, 1953, "interwar",  "politician",  "RO", "Q343376"),
    ("miron costin",         "Miron Costin",                 "M", 1633, 1691, "medieval",  "writer",      "RO", "Q715279"),
    ("marin preda",          "Marin Preda",                  "M", 1922, 1980, "communist", "writer",      "RO", "Q331085"),
    ("nicolae labis",        "Nicolae Labiș",                "M", 1935, 1956, "communist", "poet",        "RO", None),
    ("petofi sandor",        "Petőfi Sándor",                "M", 1823, 1849, "premodern", "poet",        "HU", "Q46261"),
    ("ady endre",            "Ady Endre",                    "M", 1877, 1919, "premodern", "poet",        "HU", "Q165655"),
    ("constantin brancusi",  "Constantin Brâncuși",          "M", 1876, 1957, "interwar",  "artist",      "RO", "Q44523"),
    ("spiru haret",          "Spiru Haret",                  "M", 1851, 1912, "premodern", "educator",    "RO", "Q365386"),
    ("carol i",              "Regele Carol I",               "M", 1839, 1914, "premodern", "royalty",     "RO", "Q131694"),
    ("mircea eliade",        "Mircea Eliade",                "M", 1907, 1986, "interwar",  "philosopher", "RO", "Q41614"),
    ("andrei saguna",        "Andrei Șaguna",                "M", 1809, 1873, "premodern", "clergy",      "RO", "Q432832"),
    ("gheorghe sincai",      "Gheorghe Șincai",              "M", 1754, 1816, "premodern", "historian",   "RO", "Q574767"),
    ("iancu jianu",          "Iancu Jianu",                  "M", 1787, 1842, "premodern", "outlaw",      "RO", None),
    ("burebista",            "Burebista",                    "M", None,  -44, "ancient",   "king",        "RO", "Q193389"),
    ("gheorghe lazar",       "Gheorghe Lazăr",               "M", 1779, 1823, "premodern", "educator",    "RO", "Q952971"),
    ("george toparceanu",    "George Topârceanu",            "M", 1886, 1937, "interwar",  "poet",        "RO", None),
    ("costache negri",       "Costache Negri",               "M", 1812, 1876, "1848",      "politician",  "RO", None),
    ("dimitrie bolintineanu","Dimitrie Bolintineanu",        "M", 1819, 1872, "1848",      "poet",        "RO", "Q731699"),
    ("gheorghe asachi",      "Gheorghe Asachi",              "M", 1788, 1869, "premodern", "writer",      "RO", "Q647400"),
    ("veronica micle",       "Veronica Micle",               "F", 1850, 1889, "premodern", "poet",        "RO", "Q561702"),
    ("corneliu coposu",      "Corneliu Coposu",              "M", 1914, 1995, "communist", "politician",  "RO", "Q528773"),
    ("grigore alexandrescu", "Grigore Alexandrescu",         "M", 1810, 1885, "premodern", "writer",      "RO", "Q647453"),
    ("ion minulescu",        "Ion Minulescu",                "M", 1881, 1944, "interwar",  "poet",        "RO", "Q647495"),
    ("vasile goldis",        "Vasile Goldiș",                "M", 1862, 1934, "interwar",  "politician",  "RO", "Q1375432"),
    ("barbu stefanescu delavrancea", "Barbu Ștefănescu Delavrancea", "M", 1858, 1918, "premodern", "writer", "RO", "Q647376"),
    ("george calinescu",     "George Călinescu",             "M", 1899, 1965, "interwar",  "writer",      "RO", "Q647391"),
    ("marin sorescu",        "Marin Sorescu",                "M", 1936, 1996, "communist", "writer",      "RO", "Q331063"),
    ("stefan luchian",       "Ștefan Luchian",               "M", 1868, 1916, "premodern", "painter",     "RO", "Q330905"),
    ("alecu russo",          "Alecu Russo",                  "M", 1819, 1859, "1848",      "writer",      "RO", None),
    ("alexandru lapusneanu", "Alexandru Lăpușneanu",         "M", None, 1568, "medieval",  "voievod",     "RO", None),
    ("c. a. rosetti",        "C. A. Rosetti",                "M", 1816, 1885, "1848",      "politician",  "RO", "Q647381"),
    ("gheorghe baritiu",     "Gheorghe Barițiu",             "M", 1812, 1893, "premodern", "historian",   "RO", "Q647399"),
    ("theodor aman",         "Theodor Aman",                 "M", 1831, 1891, "premodern", "painter",     "RO", "Q1388476"),
    ("barbu lautaru",        "Barbu Lăutaru",                "M", 1780, 1858, "premodern", "musician",    "RO", None),
    ("grigore ureche",       "Grigore Ureche",               "M", 1590, 1647, "medieval",  "writer",      "RO", "Q647461"),
    ("matei corvin",         "Matei Corvin",                 "M", 1443, 1490, "medieval",  "royalty",     "HU", "Q44511"),
    ("iancu de hunedoara",   "Iancu de Hunedoara",           "M", 1406, 1456, "medieval",  "military",    "RO", "Q44461"),
    ("bogdan voda",          "Bogdan Vodă I",                "M", None, 1365, "medieval",  "voievod",     "RO", None),
    ("neagoe basarab",       "Neagoe Basarab",               "M", 1459, 1521, "medieval",  "voievod",     "RO", "Q559382"),
    ("ovidiu",               "Publius Ovidius Naso",         "M",  -43,   17, "ancient",   "writer",      None, "Q7198"),
    ("vasile parvan",        "Vasile Pârvan",                "M", 1882, 1927, "interwar",  "historian",   "RO", "Q647397"),
    ("bogdan petriceicu hasdeu", "Bogdan Petriceicu Hașdeu", "M", 1838, 1907, "premodern", "writer",     "RO", "Q647407"),
    ("emil cioran",          "Emil Cioran",                  "M", 1911, 1995, "interwar",  "philosopher", "RO", "Q163294"),
    ("vasile lucaciu",       "Vasile Lucaciu",               "M", 1852, 1922, "premodern", "clergy",      "RO", "Q1375430"),
    ("petru maior",          "Petru Maior",                  "M", 1760, 1821, "premodern", "historian",   "RO", "Q575159"),
    ("stefan octavian iosif","Ștefan Octavian Iosif",        "M", 1875, 1913, "premodern", "poet",        "RO", None),
    ("maria",                "Regina Maria",                 "F", 1875, 1938, "interwar",  "royalty",     "RO", "Q159020"),
    ("ferdinand",            "Regele Ferdinand I",           "M", 1865, 1927, "interwar",  "royalty",     "RO", "Q159014"),
    ("eftimie murgu",        "Eftimie Murgu",                "M", 1805, 1870, "1848",      "revolutionary","RO", "Q647431"),
    ("ion heliade radulescu","Ion Heliade Rădulescu",        "M", 1802, 1872, "premodern", "writer",      "RO", "Q647473"),
    ("ion neculce",          "Ion Neculce",                  "M", 1672, 1745, "medieval",  "writer",      "RO", "Q647489"),
    ("camil petrescu",       "Camil Petrescu",               "M", 1894, 1957, "interwar",  "writer",      "RO", "Q647385"),
    ("negru voda",           "Negru Vodă",                   "M", None, 1290, "medieval",  "voievod",     "RO", None),
    ("cezar bolliac",        "Cezar Bolliac",                "M", 1813, 1881, "1848",      "poet",        "RO", None),
    ("g-ral eremia grigorescu", "Eremia Grigorescu",         "M", 1863, 1919, "premodern", "military",    "RO", "Q1372003"),
    ("henri coanda",         "Henri Coandă",                 "M", 1886, 1972, "interwar",  "engineer",    "RO", "Q193553"),
    ("titu maiorescu",       "Titu Maiorescu",               "M", 1840, 1917, "premodern", "writer",      "RO", "Q647519"),
    ("alexandru odobescu",   "Alexandru Odobescu",           "M", 1834, 1895, "premodern", "writer",      "RO", "Q647527"),
    ("popa sapca",           "Popa Șapcă",                   "M", 1810, 1860, "1848",      "clergy",      "RO", None),
    ("alecu russo",          "Alecu Russo",                  "M", 1819, 1859, "1848",      "writer",      "RO", None),
    ("grigore ureche",       "Grigore Ureche",               "M", 1590, 1647, "medieval",  "writer",      "RO", "Q647461"),
]

# ── NAME CATEGORIES ──────────────────────────────────────────────────────────
# (core_name_norm, category, subcategory)
CATEGORIES = [
    # abstract descriptors
    ("noua",           "abstract", "new"),
    ("mica",           "abstract", "small"),
    ("mare",           "abstract", "large"),
    ("lunga",          "abstract", "long"),
    ("scurta",         "abstract", "short"),
    ("angusta",        "abstract", "narrow"),
    # ideological / abstract
    ("tineretului",    "ideological", "youth"),
    ("sperantei",      "abstract",    "hope"),
    ("viitorului",     "abstract",    "future"),
    ("eternitatii",    "abstract",    "eternity"),
    ("progresului",    "ideological", "progress"),
    ("luminii",        "abstract",    "enlightenment"),
    ("armoniei",       "abstract",    "harmony"),
    ("anfratirii",     "ideological", "brotherhood"),
    ("prieteniei",     "abstract",    "friendship"),
    ("biruintei",      "ideological", "victory"),
    ("gloriei",        "ideological", "glory"),
    ("dreptatii",      "abstract",    "justice"),
    ("democratiei",    "ideological", "democracy"),
    ("orizontului",    "abstract",    "horizon"),
    ("orizont",        "abstract",    "horizon"),
    ("linistei",       "abstract",    "peace"),
    ("linistii",       "abstract",    "peace"),
    ("veseliei",       "abstract",    "joy"),
    ("vointei",        "abstract",    "resolve"),
    ("avantului",      "abstract",    "impetus"),
    ("renasterii",     "ideological", "rebirth"),
    ("recunostintei",  "abstract",    "gratitude"),
    ("belsugului",     "abstract",    "abundance"),
    ("dorului",        "abstract",    "longing"),
    ("doinei",         "abstract",    "folk_music"),
    ("rapsodiei",      "abstract",    "music"),
    ("melodiei",       "abstract",    "music"),
    ("baladei",        "abstract",    "music"),
    ("muncii",         "ideological", "labor"),
    ("energiei",       "abstract",    "energy"),
    ("nordului",       "abstract",    "direction"),
    ("sudului",        "abstract",    "direction"),
    ("1 decembrie 1918", "ideological", "national_day"),
    # institutional
    ("parcului",       "institutional", "park"),
    ("cimitirului",    "institutional", "cemetery"),
    ("gradinitei",     "institutional", "kindergarten"),
    ("postei",         "institutional", "post_office"),
    ("dispensarului",  "institutional", "dispensary"),
    ("spitalului",     "institutional", "hospital"),
    ("muzeului",       "institutional", "museum"),
    ("sportului",      "institutional", "sport"),
    ("strandului",     "institutional", "pool"),
    ("culturii",       "institutional", "cultural"),
    ("caminului",      "institutional", "cultural_center"),
    ("gradinilor",     "institutional", "park"),
    ("gradinii",       "institutional", "park"),
    ("serelor",        "trade",         "greenhouse"),
    # trade / industrial
    ("fabricii",       "trade",  "factory"),
    ("uzinei",         "trade",  "factory"),
    ("carierei",       "trade",  "quarry"),
    ("industriei",     "trade",  "industry"),
    ("minerilor",      "trade",  "mining"),
    ("silozului",      "trade",  "silo"),
    ("depozitelor",    "trade",  "warehouse"),
    ("depozitului",    "trade",  "warehouse"),
    ("sondei",         "trade",  "oil_well"),
    ("oborului",       "trade",  "market"),
    ("fermei",         "trade",  "farm"),
    ("brutariei",      "trade",  "bakery"),
    ("zootehniei",     "trade",  "farming"),
    ("targului",       "trade",  "market"),
    ("recoltei",       "trade",  "harvest"),
    ("ogorului",       "trade",  "agriculture"),
    ("agriculturii",   "institutional", "agriculture"),
    ("agricultori",    "occupational", "farmers"),
    ("agricultorilor", "occupational", "farmers"),
    # infrastructure
    ("digului",        "infrastructure", "embankment"),
    ("barajului",      "infrastructure", "dam"),
    ("podului",        "infrastructure", "bridge"),
    ("canalului",      "infrastructure", "canal"),
    ("cantonului",     "infrastructure", "railway"),
    ("rampei",         "infrastructure", "ramp"),
    # occupational
    ("gradinarilor",   "occupational", "gardeners"),
    ("pescarilor",     "occupational", "fishermen"),
    ("fierarilor",     "trade",        "blacksmiths"),
    ("olarilor",       "trade",        "potters"),
    ("lautarilor",     "occupational", "musicians"),
    ("meseriasilor",   "occupational", "craftsmen"),
    ("constructorului","occupational", "builder"),
    ("constructorilor","occupational", "builders"),
    ("vanatorilor",    "occupational", "hunters"),
    ("vanatorului",    "occupational", "hunter"),
    ("pompierilor",    "institutional", "firefighters"),
    ("plugarilor",     "occupational", "farmers"),
    ("vanatori",       "occupational", "hunters"),
    ("gradinarilor",   "occupational", "gardeners"),
    # commemorative
    ("pandurilor",     "commemorative", "pandurs"),
    ("panduri",        "commemorative", "pandurs"),
    ("dorobantilor",   "commemorative", "dorobanti"),
    ("dorobanti",      "commemorative", "dorobanti"),
    ("veteranilor",    "commemorative", "veterans"),
    ("aviatorilor",    "commemorative", "aviators"),
    ("dacilor",        "commemorative", "dacians"),
    ("motilor",        "commemorative", "moti_people"),
    # mythology / roman names (Black Sea resorts + Roman deities)
    ("venus",    "mythology", "roman_deity"),
    ("saturn",   "mythology", "roman_deity"),
    ("neptun",   "mythology", "roman_deity"),
    ("jupiter",  "mythology", "roman_deity"),
    ("mercur",   "mythology", "roman_deity"),
    ("uranus",   "mythology", "roman_deity"),
]

# ── PLACE REFERENCES ─────────────────────────────────────────────────────────
# (core_name_norm, place_name, place_type, country)
PLACES = [
    # rivers
    ("dunarii",       "Dunărea",        "river",         "RO"),
    ("oltului",       "Olt",            "river",         "RO"),
    ("muresului",     "Mureș",          "river",         "RO"),
    ("jiului",        "Jiu",            "river",         "RO"),
    ("bistritei",     "Bistrița",       "river",         "RO"),
    ("siretului",     "Siret",          "river",         "RO"),
    ("prutului",      "Prut",           "river",         "RO"),
    ("ialomitei",     "Ialomița",       "river",         "RO"),
    ("argesului",     "Argeș",          "river",         "RO"),
    ("somesului",     "Someș",          "river",         "RO"),
    ("crisului",      "Criș",           "river",         "RO"),
    ("cernei",        "Cerna",          "river",         "RO"),
    ("barsei",        "Bârsa",          "river",         "RO"),
    ("milcov",        "Milcov",         "river",         "RO"),
    ("siret",         "Siret",          "river",         "RO"),
    ("mures",         "Mureș",          "river",         "RO"),
    ("lotrului",      "Lotru",          "river",         "RO"),
    ("ariesului",     "Arieș",          "river",         "RO"),
    ("jiului",        "Jiu",            "river",         "RO"),
    ("prutului",      "Prut",           "river",         "RO"),
    # mountains
    ("carpati",       "Carpați",        "mountain_range","RO"),
    ("bucegi",        "Bucegi",         "mountain_range","RO"),
    ("caraiman",      "Caraiman",       "mountain_peak", "RO"),
    ("parangului",    "Parâng",         "mountain",      "RO"),
    ("rodnei",        "Munții Rodnei",  "mountain",      "RO"),
    ("piatra craiului","Piatra Craiului","mountain",     "RO"),
    # regions
    ("transilvaniei", "Transilvania",   "region",        "RO"),
    ("ardealului",    "Ardeal",         "region",        "RO"),
    ("moldovei",      "Moldova",        "region",        "RO"),
    ("olteniei",      "Oltenia",        "region",        "RO"),
    ("munteniei",     "Muntenia",       "region",        "RO"),
    ("banatului",     "Banat",          "region",        "RO"),
    ("dobrogei",      "Dobrogea",       "region",        "RO"),
    ("maramures",     "Maramureș",      "region",        "RO"),
    ("zarandului",    "Zarand",         "region",        "RO"),
    ("dacia",         "Dacia",          "ancient_region","RO"),
    # cities / resorts
    ("alba iulia",    "Alba Iulia",     "ro_city",       "RO"),
    ("bucuresti",     "București",      "ro_city",       "RO"),
    ("calarasi",      "Călărași",       "ro_city",       "RO"),
    ("fagaras",       "Făgăraș",        "ro_city",       "RO"),
    ("bicaz",         "Bicaz",          "ro_city",       "RO"),
    ("paltinis",      "Păltiniș",       "resort",        "RO"),
    ("paris",         "Paris",          "city",          "FR"),
    # battle sites
    ("oituz",         "Oituz",          "battle_site",   "RO"),
    ("marasesti",     "Mărășești",      "battle_site",   "RO"),
    ("marasti",       "Mărăști",        "battle_site",   "RO"),
    ("calugareni",    "Călugăreni",     "battle_site",   "RO"),
    ("plevnei",       "Plevna",         "battle_site",   "BG"),
    ("grivitei",      "Grivița",        "battle_site",   "BG"),
    ("grivita",       "Grivița",        "battle_site",   "BG"),
    ("razboieni",     "Războieni",      "battle_site",   "RO"),
    ("bobalna",       "Bobâlna",        "battle_site",   "RO"),
    ("posada",        "Posada",         "battle_site",   "RO"),
    ("rovine",        "Rovine",         "battle_site",   "RO"),
    ("rahovei",       "Rahova",         "battle_site",   "BG"),
    ("smardan",       "Smârdan",        "battle_site",   "RO"),
    ("islaz",         "Islaz",          "ro_village",    "RO"),
]


# ── CSV GENERATION ────────────────────────────────────────────────────────────
HEADER = [
    "core_name_norm", "freq", "judete_n", "uats_n", "sample_name", "judete_list",
    "table",
    "full_name", "gender", "birth_year", "death_year", "era", "profession",
    "nationality", "wikidata_qid",
    "term", "nature_type",
    "category", "subcategory",
    "place_name", "place_type", "country",
    "notes",
]

def row(**kw):
    r = {h: "" for h in HEADER}
    r.update(kw)
    return r

rows = []

for (cnorm, term, ntype) in NATURE:
    rows.append(row(core_name_norm=cnorm, table="nature_terms",
                    term=term, nature_type=ntype))

seen_persons = set()
for t in PERSONS:
    cnorm = t[0]
    if cnorm in seen_persons:
        continue
    seen_persons.add(cnorm)
    cnorm, full, gender, birth, death, era, prof, nat, qid = t
    rows.append(row(
        core_name_norm=cnorm, table="persons",
        full_name=full, gender=gender,
        birth_year="" if birth is None else birth,
        death_year="" if death is None else death,
        era=era, profession=prof,
        nationality=nat or "", wikidata_qid=qid or "",
    ))

seen_cats = set()
for t in CATEGORIES:
    cnorm, cat, sub = t
    if cnorm in seen_cats:
        continue
    seen_cats.add(cnorm)
    rows.append(row(core_name_norm=cnorm, table="name_categories",
                    category=cat, subcategory=sub))

seen_places = set()
for t in PLACES:
    cnorm, pname, ptype, country = t
    if cnorm in seen_places:
        continue
    seen_places.add(cnorm)
    rows.append(row(core_name_norm=cnorm, table="place_refs",
                    place_name=pname, place_type=ptype, country=country))

OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=HEADER)
    w.writeheader()
    w.writerows(rows)

print(f"Generated {len(rows)} rows → {OUT}")
print(f"  nature_terms : {sum(1 for r in rows if r['table']=='nature_terms')}")
print(f"  persons      : {sum(1 for r in rows if r['table']=='persons')}")
print(f"  name_categories: {sum(1 for r in rows if r['table']=='name_categories')}")
print(f"  place_refs   : {sum(1 for r in rows if r['table']=='place_refs')}")

if "--dry-run" not in sys.argv:
    import subprocess
    result = subprocess.run(
        ["python3", "tools/import_csv.py", str(OUT)],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print("ERRORS:", result.stderr)
        sys.exit(1)
