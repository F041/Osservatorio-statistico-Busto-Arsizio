# src/tools/sql_aggregator_tool.py
import sqlite3
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

try:
    from .wikipedia_enricher_tool import normalize_string
except ImportError:
    # Fallback se eseguito direttamente o struttura diversa
    try:
        # Potrebbe essere necessario aggiungere src/ al path
        # import sys
        # sys.path.append(str(Path(__file__).parent.parent.resolve()))
        from wikipedia_enricher_tool import normalize_string
    except ImportError:
        logging.error("IMPOSSIBILE IMPORTARE normalize_string in sql_aggregator_tool.py")
        # Definisci una funzione dummy per evitare errori, ma logga un warning critico
        def normalize_string(s):
            logging.warning("Funzione normalize_string non importata correttamente! Usando fallback base.")
            return str(s).lower().strip() if s else ""

# Configurazione logger e caricamento path DB (come prima)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
    dotenv_path = PROJECT_ROOT / '.env'
    load_dotenv(dotenv_path=dotenv_path)
    DB_ENV_VAR = os.environ.get("DATABASE_FILE", "data/database/busto_pagamenti.db")
    DB_PATH = PROJECT_ROOT / DB_ENV_VAR
    if not DB_PATH.is_file():
         logger.warning(f"File database non trovato in {DB_PATH}. Le funzioni SQL falliranno.")
         DB_PATH = None
    else:
         logger.info(f"Percorso DB per aggregazioni SQL: {DB_PATH}")
except Exception as e:
    logger.error(f"Errore config DB per aggregazioni: {e}", exc_info=True)
    DB_PATH = None

def get_total_spend_beneficiary_year(beneficiary_name: str, year: int | str) -> dict | None:
    """Calcola somma totale per beneficiario/anno (Case-Insensitive)."""
    # ... (controlli DB_PATH e parametri) ...
    conn = None; total = None; record_count = 0
    beneficiary_col = "Beneficiario"; year_col = "Anno"; amount_col = "ImportoEuro"

    try:
        conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
        year_param = int(year)

        # Usa UPPER per confronto case-insensitive sul beneficiario
        # Assicurati che i nomi colonna siano esatti!
        query = f"SELECT SUM({amount_col}), COUNT(*) FROM pagamenti WHERE UPPER({beneficiary_col}) = UPPER(?) AND {year_col} = ?"

        # Passa il nome beneficiario e il parametro anno corretto
        logger.debug(f"Esecuzione query SQL: {query} con parametri (UPPER): ('{beneficiary_name}', '{year_param}')")
        cursor.execute(query, (beneficiary_name, year_param)) # Passa il nome originale, UPPER è nella query
                                                               # oppure: cursor.execute(query, (beneficiary_name.upper(), year_param))
                                                               # Verifica quale funziona meglio con la tua versione sqlite3/python
        result = cursor.fetchone()

        if result and result[0] is not None:
            total = float(result[0]); record_count = int(result[1])
            logger.info(f"Aggregazione SQL trovata per Beneficiario='{beneficiary_name}', Anno={year_param}: Somma={total}, Righe={record_count}")
            # Ritorna usando i parametri originali o quelli usati nella query? Meglio gli originali per coerenza.
            return {"beneficiary": beneficiary_name, "year": str(year), "total_amount": total, "record_count": record_count}
        else:
             logger.info(f"Nessun pagamento trovato con aggregazione SQL per Beneficiario='{beneficiary_name}', Anno={year_param}.")
             return None

    except ValueError as e_val:
        logger.error(f"Errore conversione anno '{year}' in intero? {e_val}", exc_info=True)
        return None
    except sqlite3.Error as e:
        logger.error(f"Errore DB SQL: {e}", exc_info=True)
        return None
    except Exception as e_gen:
         logger.error(f"Errore generico SQL: {e_gen}", exc_info=True)
         return None
    finally:
        if conn: conn.close()

def find_official_beneficiary_name(query_name: str) -> str | None:
    """
    Cerca un nome nella tabella beneficiari_info usando LIKE sul nome normalizzato
    e restituisce il nome ufficiale (Beneficiario) corrispondente.
    """
    # ... (controlli DB_PATH, query_name) ...
    conn = None; official_name = None
    normalized_query_name = normalize_string(query_name)
    if not normalized_query_name: return query_name # Fallback

    try:
        conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
        # --- MODIFICA QUERY: Usa LIKE ---
        # Cerca nomi normalizzati che INIZIANO con la query normalizzata
        # Aggiungiamo '%' alla fine del parametro per il matching LIKE
        search_pattern = normalized_query_name + '%'
        query = "SELECT Beneficiario, NomeNormalizzato FROM beneficiari_info WHERE NomeNormalizzato LIKE ? ORDER BY LENGTH(NomeNormalizzato) ASC LIMIT 1"
        logger.debug(f"Esecuzione lookup SQL (LIKE): {query} con parametro: '{search_pattern}'")
        cursor.execute(query, (search_pattern,))
        result = cursor.fetchone()
        # -----------------------------

        if result:
            official_name = result[0] # Colonna Beneficiario (originale)
            found_normalized = result[1] # Colonna NomeNormalizzato trovata
            logger.info(f"Lookup (LIKE) per '{query_name}' (norm: '{normalized_query_name}') -> Trovato: '{official_name}' (norm db: '{found_normalized}')")
        else:
            logger.info(f"Lookup (LIKE) beneficiario: Nessun nome ufficiale trovato per '{query_name}' (norm: '{normalized_query_name}'). Uso originale.")
            official_name = query_name.strip()

    except sqlite3.Error as e:
        logger.error(f"Errore DB lookup beneficiario: {e}", exc_info=True)
        official_name = query_name.strip()
    except Exception as e_gen:
        logger.error(f"Errore generico lookup beneficiario: {e_gen}", exc_info=True)
        official_name = query_name.strip()
    finally:
        if conn: conn.close()

    return official_name

def get_top_suppliers_by_year(year: int | str, top_n: int = 5) -> list[dict] | None:
    """
    Trova i primi N beneficiari per importo totale speso in un anno specifico.
    Ritorna una lista di dizionari [{'Beneficiario': nome, 'TotaleSpeso': importo}] o None.
    """
    if not DB_PATH or not DB_PATH.exists():
        logger.error("Percorso DB non valido per query SQL top suppliers.")
        return None
    if not year or not top_n > 0:
         logger.warning("Anno o top_n non validi per query SQL top suppliers.")
         return None

    conn = None
    results_list = []
    beneficiary_col = "Beneficiario"; year_col = "Anno"; amount_col = "ImportoEuro"

    try:
        conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
        year_param = int(year) # Assumendo Anno sia INTEGER nel DB

        query = f"""
            SELECT {beneficiary_col}, SUM({amount_col}) as TotaleSpeso
            FROM pagamenti
            WHERE {year_col} = ?
            GROUP BY {beneficiary_col}
            HAVING TotaleSpeso > 0 -- Escludi totali nulli o zero se necessario
            ORDER BY TotaleSpeso DESC
            LIMIT ?
        """
        logger.debug(f"Esecuzione query SQL Top Suppliers: {query} con parametri: ({year_param}, {top_n})")
        cursor.execute(query, (year_param, top_n))
        results = cursor.fetchall()

        if results:
            for row in results:
                results_list.append({
                    "Beneficiario": row[0],
                    "TotaleSpeso": float(row[1])
                })
            logger.info(f"Trovati top {len(results_list)} fornitori per anno {year_param}.")
            return results_list
        else:
             logger.info(f"Nessun fornitore trovato con spesa > 0 per anno {year_param}.")
             return [] # Ritorna lista vuota se non trova nulla

    except ValueError as e_val: logger.error(f"Errore conversione anno '{year}': {e_val}"); return None
    except sqlite3.Error as e: logger.error(f"Errore DB SQL Top Suppliers: {e}"); return None
    except Exception as e_gen: logger.error(f"Errore generico SQL Top Suppliers: {e_gen}"); return None
    finally:
        if conn: conn.close()

def get_payment_count_beneficiary_year(beneficiary_name: str, year: int | str) -> dict | None:
    """
    Conta il numero di pagamenti registrati per un beneficiario in un anno specifico.
    Ritorna un dizionario {'beneficiary': nome, 'year': anno, 'record_count': numero} o None in caso di errore grave.
    """
    if not DB_PATH or not DB_PATH.exists():
        logger.error("Percorso DB non valido per query SQL conteggio pagamenti.")
        return None
    if not beneficiary_name or not year:
         logger.warning("Nome beneficiario o anno non validi per query SQL conteggio pagamenti.")
         return None # O ritorna un dizionario con errore? Per ora None.

    conn = None
    count = 0 # Default a 0
    beneficiary_col = "Beneficiario"; year_col = "Anno"

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        year_param = int(year) # Converti anno a intero

        # Usa UPPER per confronto case-insensitive sul beneficiario
        # Assicurati che i nomi colonna siano corretti (Beneficiario, Anno)
        query = f"SELECT COUNT(*) FROM pagamenti WHERE UPPER({beneficiary_col}) = UPPER(?) AND {year_col} = ?"

        logger.debug(f"Esecuzione query SQL Conteggio: {query} con parametri (UPPER): ('{beneficiary_name}', {year_param})")
        cursor.execute(query, (beneficiary_name, year_param)) # Passa il nome originale, UPPER è nella query
        result = cursor.fetchone()

        # COUNT(*) ritorna sempre una riga, anche se il conteggio è 0
        if result is not None:
            count = int(result[0])
            logger.info(f"Conteggio SQL trovato per Beneficiario='{beneficiary_name}', Anno={year_param}: Righe={count}")
        else:
            # Questo scenario è molto improbabile con COUNT(*) ma lo gestiamo per sicurezza
            logger.warning(f"Query COUNT(*) per Beneficiario='{beneficiary_name}', Anno={year_param} non ha restituito un risultato? Imposto count a 0.")
            count = 0

        # Ritorna sempre un dizionario se non ci sono stati errori gravi
        return {"beneficiary": beneficiary_name, "year": str(year), "record_count": count}

    except ValueError as e_val:
        logger.error(f"Errore conversione anno '{year}' in intero: {e_val}", exc_info=True)
        return None # Errore grave sui parametri
    except sqlite3.Error as e:
        logger.error(f"Errore DB SQL Conteggio Pagamenti: {e}", exc_info=True)
        return None # Errore grave DB
    except Exception as e_gen:
         logger.error(f"Errore generico SQL Conteggio Pagamenti: {e_gen}", exc_info=True)
         return None # Errore generico grave
    finally:
        if conn: conn.close()

# --- Test (come prima) ---
if __name__ == "__main__":
    # ... (codice di test invariato, ma ora usa la nuova funzione che ritorna un dizionario) ...
     test_beneficiary = "AGESP ATTIVITA' STRUMENTALI SRL"
     test_year = 2023
     result_dict = get_total_spend_beneficiary_year(test_beneficiary, test_year)
     print("\nTest Aggregazione:")
     if result_dict:
         amount = result_dict['total_amount']
         count = result_dict['record_count']
         amount_formatted = "{:,.2f}".format(amount).replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
         print(f"Spesa totale per '{test_beneficiary}' nel {test_year}: {amount_formatted} € ({count} record)")
     else:
         print(f"Nessuna spesa trovata per '{test_beneficiary}' nel {test_year} o errore.")
     print("\nTest Funzione Lookup Beneficiario:")
     test_names = ["agesp attività", "Agesp", "maggioli spa", "Comune B.A.", "Università Cattolica" , "Nome Inesistente"]
     for name in test_names:
        official = find_official_beneficiary_name(name)
        print(f"- Ricerca per '{name}' -> Nome ufficiale trovato: '{official}'")
     print("\nTest Top Suppliers:")
     test_year_top = 2023
     top_suppliers = get_top_suppliers_by_year(test_year_top, 5)
     if top_suppliers is not None:
        print(f"Top 5 fornitori per il {test_year_top}:")
        if top_suppliers:
            for i, supplier in enumerate(top_suppliers):
                amount_fmt = "{:,.2f}".format(supplier['TotaleSpeso']).replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
                print(f" {i+1}. {supplier['Beneficiario']} ({amount_fmt} €)")
        else:
            print("  Nessun fornitore trovato.")
     else:
        print("  Errore durante il recupero dei top suppliers.")
        print("\nTest Funzione Conteggio Pagamenti:")
     test_beneficiary_count = "AGESP ATTIVITA' STRUMENTALI SRL"
     test_year_count = 2023
     count_result = get_payment_count_beneficiary_year(test_beneficiary_count, test_year_count)
     if count_result is not None:
        print(f"- Numero pagamenti per '{count_result['beneficiary']}' nel {count_result['year']}: {count_result['record_count']}")
     else:
        print(f"- Errore durante il conteggio pagamenti per '{test_beneficiary_count}' nel {test_year_count}.")

     test_beneficiary_count_zero = "Beneficiario Inesistente Test"
     test_year_count_zero = 2023
     count_result_zero = get_payment_count_beneficiary_year(test_beneficiary_count_zero, test_year_count_zero)
     if count_result_zero is not None:
         print(f"- Numero pagamenti per '{count_result_zero['beneficiary']}' nel {count_result_zero['year']}: {count_result_zero['record_count']}")
     else:
        print(f"- Errore durante il conteggio pagamenti per '{test_beneficiary_count_zero}' nel {test_year_count_zero}.")