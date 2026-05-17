# Notebooks — Analiză în profunzime

Fiecare notebook explică un subiect editorial din datele despre numirea străzilor din România. Codul este rulabil și reproductibil — oricine poate re-executa analiza cu orice versiune a bazei de date.

## Cerințe

```bash
# Activați venv-ul proiectului
source ~/devbox/envs/240826/bin/activate

# Baza de date trebuie să existe
python3 ../build_db.py        # dacă nu există data/streets.db
python3 ../seed_lookups.py
python3 ../tools/seed_top500.py
python3 ../tools/seed_batch2.py

# Lansați Jupyter
cd notebooks/
jupyter notebook
```

## Notebooks

| Fișier | Subiect |
|--------|---------|
| `00_data_tour.ipynb` | **Tur ghidat** — schema bazei, regulile critice (`streets_dedup`, `core_name_norm`), un join concret. Punct de plecare. |
| `01_gender_gap.ipynb` | **Ecartul de gen** — 95 din 100 de români onorați sunt bărbați. Cine sunt cele 5%? |
| `02_recognition_scope.ipynb` | **Recunoaștere locală vs. globală** — Wikidata sitelinks ca proxy pentru notorietate internațională |
| `03_ideological_names.ipynb` | **Moștenirea ideologică** — Tokeni comuniști, distribuție județeană, tipare |
| `04_nature_themes.ipynb` | **Dominanța naturii** — Flori și copaci vs. voievozi și poeți |
| `05_regional_patterns.ipynb` | **Amprente județene** — Ce face fiecare județ altfel |

## Notă metodologică

Toate notebook-urile se conectează la `../data/streets.db` (calea relativă față de directorul `notebooks/`). Baza de date este regenerabilă din sursă — nu este tracked în git.
