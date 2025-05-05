# src/run_enrichment.py

import pandas as pd
import sqlite3
from pathlib import Path
import logging
import time
import sys
import re
from tqdm import tqdm # Per una barra di progresso carina

# Importa le funzioni dal tool
try:
    # Assumendo che run_enrichment.py sia in src/ e il tool in src/tools/
    from tools.wikipedia_enricher_tool import get_wikipedia_summary, normalize_string
except ImportError:
    # Gestisci il caso in cui l'importazione diretta/relativa fallisca
    # Questo blocco prova ad aggiungere 'src' al path se necessario
    script_dir = Path(__file__).parent.resolve()
    src_dir = script_dir
    if str(src_dir) not in sys.path:
         sys.path.append(str(src_dir))
    try:
        from tools.wikipedia_enricher_tool import get_wikipedia_summary, normalize_string
    except ImportError as e:
        logging.critical(f"Errore critico: Impossibile importare da tools.wikipedia_enricher_tool. Assicurati che esista e sia nel PYTHONPATH. Dettagli: {e}")
        sys.exit(1)


# Configurazione Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Percorsi e Costanti ---
try:
    PROJECT_ROOT = Path(__file__).parent.parent.resolve()
    PROCESSED_CSV = PROJECT_ROOT / "data" / "processed_data" / "processed_pagamenti.csv"
    ENRICHED_DIR = PROJECT_ROOT / "data" / "enriched_data"
    ENRICHED_CSV = ENRICHED_DIR / "beneficiari_info.csv"
    DB_PATH = PROJECT_ROOT / "data" / "database" / "busto_pagamenti.db"
    DB_TABLE_NAME = "beneficiari_info"
    WIKI_REQUEST_DELAY = 0.5 # Riduci a tuo rischio (es. 0.5), ma 1.0 è più sicuro
except NameError:
    PROJECT_ROOT = Path('.').resolve()
    PROCESSED_CSV = PROJECT_ROOT / "data" / "processed_data" / "processed_pagamenti.csv"
    ENRICHED_DIR = PROJECT_ROOT / "data" / "enriched_data"
    ENRICHED_CSV = ENRICHED_DIR / "beneficiari_info.csv"
    DB_PATH = PROJECT_ROOT / "data" / "database" / "busto_pagamenti.db"
    DB_TABLE_NAME = "beneficiari_info"
    WIKI_REQUEST_DELAY = 0.5
    logging.warning(f"__file__ non definito, PROJECT_ROOT impostato su: {PROJECT_ROOT}")

ENRICHED_DIR.mkdir(parents=True, exist_ok=True)

# --- Funzione di Filtraggio ---
# Definisci qui le keyword che indicano una società/ente (e quindi da NON skippare)
ORG_KEYWORDS = [
    'spa', 'srl', 'snc', 'sas', 'societa', 'cooperativa', 'onlus',
    'associazione', 'assne', 'asd', 'aps', 'odv', 'ets',
    'comune', 'regione', 'provincia', 'ministero', 'agenzia', 'ente',
    'asst', 'ats', 'aler', 'inps', 'inail', 'aci', 'enel', 'tim', 'poste',
    'istituto', 'fondazione', 'consorzio', 'cral', 'scuola', 'liceo', 'universita',
    'parrocchia', 'diocesi', 'consultorio', 'camerale', 'banca', 'credito',
    'sindacato', 'confederazione', 'federazione', 'cgil', 'cisl', 'uil',
    'unione', 'lega', 'club', 'gruppo', 'comitato', 'centro', 'azienda',
    'servizi', 'system', 'group', 'editore', 'editrice', 'grafica', 'grafiche',
    'holding', 'assicurazioni', 'brico', 'market', 'energy', 'pharma',
    'studio legale', 'architetti', 'ingegneri', 'geometra', 'commercialisti',
    'fabbrica', 'industria', 'tipografia', 'legatoria', 'carrozzeria', 'autofficina',
    'farmacia', 'ortopedia', 'laboratorio', 'clinica', 'ospedale',
     # Aggiungi altre keyword rilevanti che noti
]
# Converti in set per ricerche veloci
ORG_KEYWORDS_SET = set(ORG_KEYWORDS)

# Definisci termini generici da skippare sempre
GENERIC_TERMS_TO_SKIP = {'diversi', 'dipendenti comunali', 'dipendneti comunali',
                         'economo comunale', 'erario stato', 'diversi ufficio'}

def should_skip_wikipedia_search(original_name: str, normalized_name: str) -> bool:
    """
    Decide se skippare la ricerca Wikipedia basandosi su pattern e keyword.
    Ritorna True se la ricerca va saltata, False altrimenti.
    """
    # 1. Salta termini generici esatti
    if normalized_name in GENERIC_TERMS_TO_SKIP:
        return True

    # 2. Salta nomi che sembrano persone nel formato "Cognome, Nome" (con virgolette opzionali)
    # Regex: Inizia con opzionali virgolette/spazi, poi lettere/spazi, una virgola, lettere/spazi,
    # opzionali asterischi o altro, e finisce con opzionali virgolette/spazi.
    if re.match(r'^\s*"?[\w\s\'’-]+,\s*[\w\s\'’-]+(?:[\*\s-]+.*)?"?\s*$', original_name, re.IGNORECASE):
         # Esempio: "Cognome, Nome", " Cognome , Nome ", "Cognome, Nome***123", " Cognome , Nome - VEDI COD"
         # logger.debug(f"Skipping '{original_name}' (pattern Cognome, Nome)")
         return True

    # 3. Salta nomi che contengono "***" o pattern sospetti
    if "***" in original_name or "vedi cod" in normalized_name or "estinto dal" in normalized_name:
        return True

    # 4. Salta nomi che iniziano con "Condominio"
    if normalized_name.startswith("condominio"):
        return True

    # 5. NON skippare se contiene keyword organizzative/societarie
    # Controlla se ALMENO UNA parola nel nome normalizzato è una keyword nota
    # Questo aiuta a mantenere nomi come "Rossi SRL" o "Associazione Verdi"
    # senza filtrarli come potenziali nomi propri.
    if any(word in ORG_KEYWORDS_SET for word in normalized_name.split()):
        return False # Contiene keyword -> PROVA A CERCARE

    # 6. Euristica per nomi propri "Nome Cognome" (se non già skippato o identificato come org)
    # Se ha 2 o 3 parole, tutte iniziano con Maiuscola (nell'originale),
    # e non contiene numeri o caratteri strani (a parte spazi/apostrofi/trattini)
    # Allora è PROBABILE sia un nome proprio. Più rischioso.
    words = original_name.strip().split()
    # if 1 < len(words) < 4 and all(w[0].isupper() for w in words) and re.match(r'^[A-Za-zÀ-ÿ\s\'’-]+$', original_name):
    #    logger.debug(f"Skipping '{original_name}' (euristica Nome Cognome)")
    #    return True
    # Commentato perché potrebbe dare troppi falsi negativi. Ci affidiamo di più
    # alle keyword organizzative e al pattern "Cognome, Nome".

    # 7. Default: Non skippare (prova la ricerca)
    return False


def run_beneficiary_enrichment():
    logger.info("--- Avvio Script Arricchimento Beneficiari (con Filtri) ---")

    # 1. Leggi CSV e ottieni unici (invariato)
    try:
        logger.info(f"Lettura file pagamenti: {PROCESSED_CSV}")
        df_pagamenti = pd.read_csv(PROCESSED_CSV, usecols=['Beneficiario'], encoding='utf-8-sig')
        beneficiari_unici = df_pagamenti['Beneficiario'].dropna().astype(str).str.strip().unique()
        beneficiari_unici = [b for b in beneficiari_unici if b]
        logger.info(f"Trovati {len(beneficiari_unici)} beneficiari unici iniziali.")
        if not beneficiari_unici: return
    except Exception as e:
        logger.error(f"Errore lettura CSV pagamenti: {e}", exc_info=True)
        return

    # 2. Normalizzazione e Raggruppamento (invariato)
    logger.info("Normalizzazione e raggruppamento beneficiari...")
    beneficiary_groups = {}
    beneficiary_to_normalized = {}
    count_normalization_failed = 0
    for b_original in beneficiari_unici:
        normalized_b = normalize_string(b_original)
        if not normalized_b:
             logger.warning(f"Normalizzazione fallita o vuota per: '{b_original}'")
             count_normalization_failed += 1
             continue
        beneficiary_to_normalized[b_original] = normalized_b
        if normalized_b not in beneficiary_groups: beneficiary_groups[normalized_b] = []
        beneficiary_groups[normalized_b].append(b_original)
    total_groups = len(beneficiary_groups)
    logger.info(f"Raggruppati in {total_groups} gruppi normalizzati. Fallimenti norm.: {count_normalization_failed}.")

    # 3. Carica Cache (Beneficiari già presenti nel CSV di output CON STATUS VALIDO)
    already_enriched_normalized = {}
    if ENRICHED_CSV.exists():
        try:
            df_existing = pd.read_csv(ENRICHED_CSV, encoding='utf-8-sig')
            logger.info(f"Lettura cache da {ENRICHED_CSV}...")
            cached_count = 0
            for _, row in df_existing.iterrows():
                 norm_name = row.get('NomeNormalizzato')
                 if not norm_name or pd.isna(norm_name):
                     norm_name = normalize_string(row['Beneficiario'])

                 status = row.get('LookupStatus')
                 # --- MODIFICA CACHING: Considera valido solo 'found' o 'skipped_filter' ---
                 # Ignora 'not_found', 'error', 'invalid_input', 'disambiguation' (se lo aggiungeremo)
                 # Così verranno ritentati nella prossima run.
                 if status in ['found', 'skipped_filter', 'cached']: # 'cached' aggiunto per coerenza interna
                     if norm_name and norm_name not in already_enriched_normalized:
                         already_enriched_normalized[norm_name] = {
                             'summary': row.get('WikipediaSummary'),
                             'url': row.get('WikipediaURL'),
                             'status': status # Mantieni lo status originale
                         }
                         cached_count +=1
                 #------------------------------------------------------------------------

            logger.info(f"Caricati {cached_count} gruppi normalizzati validi dalla cache CSV.")
        except Exception as e:
            logger.warning(f"Impossibile leggere o processare cache CSV {ENRICHED_CSV}: {e}")

    # 4. Filtra i gruppi da cercare (invariato)
    groups_to_search = {}
    skipped_groups = {}
    for norm_name, variants in beneficiary_groups.items():
         representative_name = max(variants, key=len)
         if should_skip_wikipedia_search(representative_name, norm_name):
             skipped_groups[norm_name] = variants
         else:
             # Cerca solo se non è già nella cache con status 'found' o 'skipped'
             if norm_name not in already_enriched_normalized or \
                already_enriched_normalized[norm_name].get('status') not in ['found', 'skipped_filter']:
                 groups_to_search[norm_name] = variants
             else:
                 # Era nella cache ma non va cercato di nuovo
                 skipped_groups[norm_name] = variants # Trattalo come skippato per questa run

    total_groups_to_search = len(groups_to_search)
    total_groups_skipped = len(skipped_groups)
    # Log aggiornato per chiarezza
    logger.info(f"Filtraggio e Cache: {total_groups_to_search} gruppi verranno CERCATI/RITENTATI via API, {total_groups_skipped} gruppi sono SKIPPATI (filtro o cache valida).")


    # 5. Arricchisci solo i gruppi filtrati e non in cache valida (con caching)
    enriched_data_list = []
    api_calls_made = 0
    cache_hits_in_loop = 0 # Contatore separato per i cache hit DENTRO il loop

    logger.info("Inizio arricchimento tramite Wikipedia per gruppi filtrati/da ritentare...")

    # Itera sui gruppi con tqdm (ora il totale è corretto per le chiamate API)
    for normalized_name, original_variants in tqdm(groups_to_search.items(), total=total_groups_to_search, desc="Cercando/Ritentando"):

        wiki_result = {'summary': None, 'url': None, 'status': 'unknown'} # Default

        # Non serve più ricontrollare la cache qui, perché abbiamo già filtrato `groups_to_search`
        # Procediamo direttamente alla chiamata API per questi gruppi

        representative_name = max(original_variants, key=len)
        logger.debug(f"Chiamata API per gruppo '{normalized_name}' (usando '{representative_name}')...")

        # --- Chiamata API ---
        wiki_result = get_wikipedia_summary(representative_name) # O usa normalized_name
        api_calls_made += 1 # Incrementa qui perché stiamo facendo la chiamata

        # Aggiorna cache in memoria per evitare chiamate duplicate nella stessa run
        already_enriched_normalized[normalized_name] = wiki_result

        # Pausa SOLO dopo una chiamata API
        time.sleep(WIKI_REQUEST_DELAY)

        # Aggiungi record per OGNI variante originale nel gruppo APPENA CERCATO
        for original_beneficiario in original_variants:
            enriched_data_list.append({
                'Beneficiario': original_beneficiario,
                'NomeNormalizzato': normalized_name,
                'NomeUsatoPerRicerca': representative_name, # Ora sappiamo che è stato cercato
                'WikipediaSummary': wiki_result['summary'],
                'WikipediaURL': wiki_result['url'],
                'LookupStatus': wiki_result['status']
            })

    # Aggiungi i record dalla CACHE (quelli validi trovati all'inizio) e dagli SKIPPATI
    processed_in_loop = set(groups_to_search.keys()) # Nomi normalizzati processati nel loop

    # Aggiungi dalla cache iniziale (se non sono stati sovrascritti da una nuova ricerca nel loop)
    for normalized_name, cached_data in already_enriched_normalized.items():
         if normalized_name not in processed_in_loop: # Era nella cache valida E non è stato ritentato
             if normalized_name in beneficiary_groups: # Assicurati che il gruppo esista ancora
                 original_variants = beneficiary_groups[normalized_name]
                 status_to_save = cached_data.get('status', 'cached')
                 for original_beneficiario in original_variants:
                      enriched_data_list.append({
                          'Beneficiario': original_beneficiario,
                          'NomeNormalizzato': normalized_name,
                          'NomeUsatoPerRicerca': 'N/A (cached)',
                          'WikipediaSummary': cached_data['summary'],
                          'WikipediaURL': cached_data['url'],
                          'LookupStatus': status_to_save
                      })

    # Aggiungi gli skippati dal filtro iniziale
    for normalized_name, original_variants in skipped_groups.items():
         # Assicurati di non aggiungerli se sono già stati aggiunti dalla cache valida
         if normalized_name not in already_enriched_normalized or \
            already_enriched_normalized[normalized_name].get('status') not in ['found', 'cached']:
              for original_beneficiario in original_variants:
                  enriched_data_list.append({
                      'Beneficiario': original_beneficiario,
                      'NomeNormalizzato': normalized_name,
                      'NomeUsatoPerRicerca': 'N/A (skipped)',
                      'WikipediaSummary': None,
                      'WikipediaURL': None,
                      'LookupStatus': 'skipped_filter'
                  })


    logger.info(f"Arricchimento completato. Chiamate API Wikipedia effettuate in questa run: {api_calls_made}.")

    # 6. Crea DataFrame finale e salva 
    if not enriched_data_list:
        logger.warning("Nessun dato arricchito generato.")
        return

    df_enriched = pd.DataFrame(enriched_data_list)
    column_order = ['Beneficiario', 'NomeNormalizzato', 'NomeUsatoPerRicerca', 'LookupStatus', 'WikipediaURL', 'WikipediaSummary']
    df_enriched = df_enriched[column_order]

    try:
        logger.info(f"Salvataggio dati arricchiti completi in: {ENRICHED_CSV} (sovrascrittura)")
        df_enriched.to_csv(ENRICHED_CSV, index=False, encoding='utf-8-sig')
        logger.info("Salvataggio CSV completato.")
    except IOError as e:
        logger.error(f"Errore salvataggio CSV: {e}", exc_info=True)

    # 7. Carica nel DB (invariato, ma aggiungi NomeNormalizzato se non c'è)
    conn = None
    try:
        logger.info(f"Connessione al database SQLite: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        logger.info(f"Scrittura dati nella tabella '{DB_TABLE_NAME}' (sostituzione)...")
        dtype_mapping = {
            'Beneficiario': 'TEXT',
            'NomeNormalizzato': 'TEXT', # Aggiunta colonna
            'NomeUsatoPerRicerca': 'TEXT', # Aggiunta colonna
            'LookupStatus': 'TEXT',
            'WikipediaURL': 'TEXT',
            'WikipediaSummary': 'TEXT'
        }
        df_enriched.to_sql(DB_TABLE_NAME, conn, if_exists='replace', index=False, dtype=dtype_mapping)
        logger.info(f"Dati scritti con successo.")

        cursor = conn.cursor()
        logger.info(f"Creazione indici su tabella '{DB_TABLE_NAME}'...")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_beneficiario ON {DB_TABLE_NAME} (Beneficiario);")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_nome_normalizzato ON {DB_TABLE_NAME} (NomeNormalizzato);")
        conn.commit()
        logger.info("Indici creati.")

        count = pd.read_sql(f"SELECT COUNT(*) FROM {DB_TABLE_NAME}", conn).iloc[0,0]
        logger.info(f"Verifica: la tabella '{DB_TABLE_NAME}' contiene {count} righe.")

    except Exception as e:
        logger.error(f"Errore SQLite o DB: {e}", exc_info=True)
    finally:
        if conn: conn.close(); logger.info("Connessione DB chiusa.")

    logger.info("--- Script Arricchimento Beneficiari Completato ---")

# --- Esecuzione ---
if __name__ == "__main__":
    run_beneficiary_enrichment()