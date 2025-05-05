import wikipediaapi
import logging
import time
import re
import unicodedata

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- FUNZIONE DI NORMALIZZAZIONE (ASSICURATI SIA QUESTA) ---
def normalize_string(s):
    # ... (codice robusto come nel messaggio precedente) ...
    if not s: return ""
    try:
        nfkd_form = unicodedata.normalize('NFKD', s.lower())
        s = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    except TypeError:
        s = str(s).lower()
    s = re.sub(r'\b(srl|spa|snc|sas|s\.r\.l|s\.p\.a|s\.n\.c|s\.a\.s)\b\.?', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[.,;:!?\'"(){}\[\]]', '', s)
    s = re.sub(r'[‘’`´]', '', s)
    s = re.sub(r'[-–—]', ' ', s)
    s = s.replace('/', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s
# ----------------------------------------------------------

# Inizializza API Wikipedia
wiki_wiki = wikipediaapi.Wikipedia(
    language='it',
    user_agent='OsservatorioStatisticoBustoArsizioBot/1.0 (...)' # AGGIORNA!
)

def get_wikipedia_summary(term: str, summary_chars: int = 500) -> dict:
    """
    Cerca un termine su Wikipedia Italia e restituisce un riassunto e URL.
    Include fallback e logging migliorato.
    """
    default_result = {'summary': None, 'url': None, 'status': 'unknown'}
    if not term or not isinstance(term, str) or term.strip() == "":
        default_result['status'] = 'invalid_input'
        return default_result

    original_term_cleaned = term.strip() # Usiamo l'originale pulito come fallback
    normalized_search_term = normalize_string(original_term_cleaned)
    if not normalized_search_term:
        normalized_search_term = original_term_cleaned # Usa originale se normalizzazione fallisce

    search_terms_to_try = [normalized_search_term]
    # Aggiungi l'originale (pulito) come seconda opzione se diverso dal normalizzato
    if original_term_cleaned.lower() != normalized_search_term and original_term_cleaned not in search_terms_to_try:
         search_terms_to_try.append(original_term_cleaned)
    # Potresti aggiungere altre varianti qui (es. senza S.P.A./SRL)

    for current_search_term in search_terms_to_try:
        logger.debug(f"Tentativo ricerca Wikipedia per: '{current_search_term}' (Originale: '{term}')")
        try:
            page = wiki_wiki.page(current_search_term)

            # --- Log di Debug per capire cosa trova la libreria ---
            if not page.exists():
                 logger.debug(f"page.exists()=False per '{current_search_term}'. Info Page Object: Title='{page.title}', Namespace={page.namespace}")
                 # Qui potresti controllare page.links o altro se la libreria lo espone facilmente
                 # per vedere se è una pagina di disambiguazione o suggerimenti
                 # if 'disambigua' in page.categories: # Esempio ipotetico
                 #     logger.info(f"Pagina '{current_search_term}' è una disambiguazione.")
                 #     default_result['status'] = 'disambiguation'
                 #     return default_result # Esce dal loop se trova disambiguazione
                 continue # Prova il prossimo termine nella lista search_terms_to_try

            # --- Pagina Esiste ---
            logger.info(f"Pagina trovata per '{current_search_term}': {page.fullurl}")
            summary = page.summary[:summary_chars]
            if len(page.summary) > summary_chars: summary += "..."

            return {
                'summary': summary,
                'url': page.fullurl,
                'status': 'found'
            }

        except Exception as e:
            logger.error(f"Errore durante ricerca Wikipedia per '{current_search_term}': {e}", exc_info=False) # Meno verboso nel log
            default_result['status'] = 'error'
            # Non ritentare se c'è un errore API, esci dal loop
            return default_result

    # Se il loop finisce senza trovare nulla
    logger.info(f"Pagina non trovata per nessuna variante di '{term}'.")
    default_result['status'] = 'not_found'
    return default_result

# Blocco per testare la funzione se esegui direttamente questo file
if __name__ == '__main__':
    print("Test della funzione get_wikipedia_summary:")

    test_terms = ["AGESP", "Regione Lombardia", "Comune di Busto Arsizio", "AziendaInesistenteXYZ123"]
    for term in test_terms:
        print(f"\n--- Test: '{term}' ---")
        result = get_wikipedia_summary(term)
        print(f"  Status: {result['status']}")
        print(f"  URL: {result['url']}")
        print(f"  Summary: {result['summary']}")
        time.sleep(1) # Piccola pausa tra le richieste di test