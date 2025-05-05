import logging
import os
import time
from pathlib import Path

import chromadb
import google.generativeai as genai
import pandas as pd
from dotenv import load_dotenv
from google.api_core import exceptions as google_exceptions

# --- Configurazione Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Caricamento Configurazione ---
try:
    load_dotenv() # Carica da .env nella root del progetto
    # --- Recupera configurazioni essenziali ---
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    CHROMA_DB_PATH = os.environ.get("CHROMA_DB_PATH", "data/database/chroma_db_pagamenti")
    CHROMA_COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION_NAME", "pagamenti_busto")
    GEMINI_EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")
    PROCESSED_CSV_PATH_FROM_ENV = os.environ.get("PROCESSED_CSV_FILE", "data/processed_data/processed_pagamenti.csv")
    DEFAULT_CHUNK_SIZE = int(os.environ.get("DEFAULT_CHUNK_SIZE_WORDS", 250))
    DEFAULT_CHUNK_OVERLAP = int(os.environ.get("DEFAULT_CHUNK_OVERLAP_WORDS", 40))
    BATCH_SIZE = 100 # Quanti documenti processare per batch (per API embedding e ChromaDB)

    # Costruisci percorsi assoluti (assumendo che lo script sia in src/)
    PROJECT_ROOT = Path(__file__).parent.parent.resolve()
    processed_csv_full_path = PROJECT_ROOT / PROCESSED_CSV_PATH_FROM_ENV  
    chroma_db_full_path = PROJECT_ROOT / CHROMA_DB_PATH

    # Verifica configurazioni critiche
    if not GOOGLE_API_KEY: raise ValueError("GOOGLE_API_KEY non trovata nel file .env")
    logger.info(f"Configurazione caricata: Modello Embedding='{GEMINI_EMBEDDING_MODEL}', Path ChromaDB='{chroma_db_full_path}', Collezione='{CHROMA_COLLECTION_NAME}', CSV Processato='{processed_csv_full_path}'")

except (ValueError, KeyError, TypeError) as e:
    logger.critical(f"Errore critico nella configurazione: {e}. Assicurati che .env esista e contenga le variabili necessarie.", exc_info=True)
    exit(1)

# --- Funzioni Helper (Chunking & Embedding - Adattate) ---

# Costanti per Embedding API
TASK_TYPE_DOCUMENT = "retrieval_document"

def safe_parse_float_for_index(value):
    """
    Parsa un valore in float, rimuovendo solo € e spazi.
    Assume che il punto (.) sia il separatore decimale.
    Ritorna float o None.
    """
    if value is None: return None
    if isinstance(value, (int, float)): return float(value)
    if not isinstance(value, str): value = str(value)

    # Logica corretta per formato XXX.YY: Rimuovi solo € e spazi
    cleaned_text = value.replace("€", "").strip()

    if cleaned_text == "" or cleaned_text == "-": return None

    try:
        # Conversione diretta a float, il punto è il decimale
        return float(cleaned_text)
    except ValueError:
        # Logga in debug per non intasare
        logger.debug(f"Conversione float fallita (ValueError) per '{value}' (pulito: '{cleaned_text}')")
        return None
    except Exception as e:
        logger.error(f"Errore imprevisto conversione float per '{value}': {e}", exc_info=True)
        return None

def split_text_into_chunks(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
) -> list[str]:
    """Divide un testo lungo in chunk basandosi su parole."""
    if not isinstance(text, str) or not text.strip(): return [] # Gestisce None o stringhe vuote
    words = text.split()
    if len(words) <= chunk_size: return [text]

    chunks = []
    start_index = 0
    step = max(1, chunk_size - chunk_overlap) # Assicura avanzamento minimo

    while start_index < len(words):
        end_index = min(start_index + chunk_size, len(words))
        chunks.append(" ".join(words[start_index:end_index]))
        start_index += step

    #logger.debug(f"Diviso testo ({len(words)} parole) in {len(chunks)} chunk.")
    return chunks

def get_gemini_embeddings_batch(
    texts: list[str],
    model_name: str = GEMINI_EMBEDDING_MODEL,
    task_type: str = TASK_TYPE_DOCUMENT
) -> list[list[float]] | None:
    """
    Genera embeddings per un batch di testi usando Gemini.
    Gestisce retries e rate limiting di base.
    Restituisce una lista di embeddings o None in caso di fallimento persistente.
    """
    if not texts: return []
    retries = 3
    delay = 5
    embeddings = None

    for attempt in range(retries):
        try:
            # Nota: Assumiamo genai.configure(api_key=...) sia stato chiamato all'inizio
            result = genai.embed_content(
                model=model_name,
                content=texts,
                task_type=task_type
            )
            embeddings = result.get('embedding', [])
            if embeddings and len(embeddings) == len(texts):
                #logger.debug(f"Embedding batch ottenuto con successo (tentativo {attempt + 1}).")
                return embeddings # Successo
            else:
                 logger.error(f"Risposta API embed_content non valida o incompleta (tentativo {attempt + 1}). Embeddings ricevuti: {len(embeddings) if embeddings else 0}/{len(texts)}")
                 # Non fare retry subito, potrebbe essere un problema del contenuto

        except google_exceptions.ResourceExhausted as e:
            logger.warning(f"Rate limit API (tentativo {attempt + 1}/{retries}). Attesa {int(delay)}s...")
            time.sleep(delay)
            delay *= 1.5 # Backoff esponenziale
        except Exception as e:
            logger.error(f"Errore chiamata embed_content (tentativo {attempt + 1}/{retries}): {e}", exc_info=True)
            time.sleep(delay) # Attendi anche per altri errori
            delay *= 1.5

        if attempt == retries - 1: # Se siamo all'ultimo tentativo
             logger.error(f"Fallimento generazione embedding batch dopo {retries} tentativi.")
             return None # Fallimento persistente

    return None # Non dovrebbe arrivare qui, ma per sicurezza


# --- Funzione Principale di Indicizzazione ---
def index_pagamenti_to_chroma():
    """Legge i pagamenti dal CSV, genera embeddings e li indicizza in ChromaDB."""
    logger.info("--- Avvio Script Indicizzazione Pagamenti in ChromaDB ---")

    # 1. Configura Google Generative AI Client
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        logger.info("Client Google Generative AI configurato.")
    except Exception as e:
        logger.critical(f"Fallimento configurazione Google Generative AI: {e}", exc_info=True)
        return False # Interrompi se la configurazione base fallisce

    # 2. Leggi i dati processati
    try:
        logger.info(f"Lettura dati da: {processed_csv_full_path}")
        # Leggi specificando dtypes per colonne potenzialmente ambigue
        dtype_spec = {
            'NumeroMandato': 'str', # Leggi come stringa per sicurezza
            'Anno': 'str',
            'CIG': 'str',
            'Beneficiario': 'str',
            'ImportoEuro': 'str', 
            'DescrizioneMandato': 'str',
            'NomeFileOrigine': 'str'
        }
        df = pd.read_csv(processed_csv_full_path,                          
                         dtype=dtype_spec, 
                         keep_default_na=False) # keep_default_na=False per evitare che stringhe vuote diventino NaN
        # Riempi eventuali NaN rimanenti (improbabile con keep_default_na=False) con stringa vuota
        df.fillna('', inplace=True)
        df.info() 
        logger.info(f"Letti {len(df)} record di pagamenti dal CSV.")
        if df.empty:
            logger.warning("Il file CSV dei pagamenti è vuoto. Nessuna indicizzazione da eseguire.")
            return True # Considera successo perché non c'è nulla da fare
    except FileNotFoundError:
        logger.error(f"File CSV processato non trovato: {processed_csv_full_path}")
        return False
    except Exception as e:
        logger.error(f"Errore durante la lettura del CSV: {e}", exc_info=True)
        return False

    # 3. Inizializza ChromaDB Client e Collezione
    try:
        logger.info(f"Inizializzazione ChromaDB client persistente in: {chroma_db_full_path}")
        # Assicurati che la directory esista
        chroma_db_full_path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(chroma_db_full_path))

        logger.info(f"Ottenimento/Creazione collezione ChromaDB: '{CHROMA_COLLECTION_NAME}'")
        # Potresti aggiungere metadati alla collezione se utile, es. {'hnsw:space': 'cosine'}
        collection = client.get_or_create_collection(name=CHROMA_COLLECTION_NAME)
        logger.info(f"Collezione '{collection.name}' pronta. Elementi attuali: {collection.count()}")
    except Exception as e:
        logger.error(f"Errore durante inizializzazione ChromaDB o collezione: {e}", exc_info=True)
        return False

    # 4. Processa e Indicizza i dati in Batch
    total_pagamenti = len(df)
    processed_count = 0
    failed_pagamenti_indices = []

    logger.info(f"Inizio indicizzazione di {total_pagamenti} pagamenti in batch da {BATCH_SIZE}...")

    for i in range(0, total_pagamenti, BATCH_SIZE):
        batch_df = df.iloc[i:i + BATCH_SIZE]
        logger.info(f"Processo batch {i // BATCH_SIZE + 1}/{(total_pagamenti + BATCH_SIZE - 1) // BATCH_SIZE} (Indici: {i}-{i + len(batch_df) - 1})")

        batch_chunks = []
        batch_metadatas = []
        batch_ids = []
        original_indices = [] # Per tenere traccia degli indici originali del DataFrame

        # Prepara chunk, metadati e ID per il batch
        for idx, row in batch_df.iterrows():
            # Combina campi testuali per creare il "documento" da indicizzare
            # Puoi scegliere quali campi sono più significativi
            doc_text = f"Anno: {row.get('Anno', '')}. Beneficiario: {row.get('Beneficiario', '')}. Descrizione: {row.get('DescrizioneMandato', '')}"
            doc_text = ' '.join(doc_text.split())

            if not doc_text:
                logger.warning(f"Pagamento indice {idx} saltato: testo combinato vuoto.")
                continue

            chunks = split_text_into_chunks(doc_text, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP)

            if not chunks:
                logger.warning(f"Pagamento indice {idx} saltato: nessun chunk generato dal testo.")
                continue

            for chunk_idx, chunk_text in enumerate(chunks):
                original_indices.append(idx) # Salva indice originale
                batch_chunks.append(chunk_text)
                chunk_id = f"pag_{idx}_chunk_{chunk_idx}" # ID univoco per il chunk
                batch_ids.append(chunk_id)

                # Prepara metadati per ChromaDB (SOLO stringhe, numeri o booleani)
                metadata = {
                    "original_index": str(idx), # Salva come stringa
                    "chunk_index": str(chunk_idx),
                    "anno": str(row.get('Anno', '')), # Assicura sia stringa
                    "numero_mandato": str(row.get('NumeroMandato', '')), # Assicura sia stringa
                    "beneficiario": str(row.get('Beneficiario', '')),
                    # L'importo potrebbe essere utile, ma deve essere float/int o stringa.
                    # Proviamo a convertirlo, con fallback a stringa
                    "importo_str": str(row.get('ImportoEuro', '')), # Salva sempre come stringa per sicurezza
                    "descrizione": str(row.get('DescrizioneMandato', ''))[:500], # Limita lunghezza per sicurezza metadati
                    "file_origine": str(row.get('NomeFileOrigine', ''))
                    # Aggiungi altri metadati utili qui, assicurandoti siano tipi validi
                }
                # Tentativo conversione importo a float per eventuale filtro numerico
                try:
                    importo_float_value = safe_parse_float_for_index(row.get('ImportoEuro', ''))
                    if importo_float_value is not None:
                        metadata['importo_float'] = importo_float_value # Aggiungi solo se la conversione ha avuto successo
                except Exception as e_proc_float: # Cattura eventuali errori nella funzione stessa
                    logger.error(f"Errore in safe_parse_float_for_index per valore '{row.get('ImportoEuro', '')}': {e_proc_float}", exc_info=True)
                    # Non aggiungere il campo float se c'è stato un errore grave
                    pass # Il campo 'importo_float' non verrà aggiunto a metadata se fallisce
                
                batch_metadatas.append(metadata)

        if not batch_chunks:
            logger.info(f"Batch {i // BATCH_SIZE + 1}: Nessun chunk valido da processare.")
            continue

        # Genera embeddings per il batch
        logger.info(f"Richiesta embedding per {len(batch_chunks)} chunk del batch...")
        batch_embeddings = get_gemini_embeddings_batch(batch_chunks)

        if batch_embeddings is None:
            logger.error(f"Fallimento generazione embedding per batch {i // BATCH_SIZE + 1}. Salto questo batch.")
            # Aggiungi tutti gli indici originali di questo batch ai falliti
            failed_pagamenti_indices.extend(list(set(original_indices))) # set per evitare duplicati
            continue

        # Upsert in ChromaDB
        try:
            logger.info(f"Esecuzione upsert su ChromaDB per {len(batch_ids)} elementi...")
            collection.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                documents=batch_chunks # Salva anche il testo del chunk
            )
            processed_count += len(batch_df) # Incrementa del numero di pagamenti nel batch DF
            logger.info(f"Upsert batch {i // BATCH_SIZE + 1} completato.")
        except Exception as e:
            logger.error(f"Errore durante upsert ChromaDB per batch {i // BATCH_SIZE + 1}: {e}", exc_info=True)
            # Aggiungi tutti gli indici originali di questo batch ai falliti
            failed_pagamenti_indices.extend(list(set(original_indices)))

    # 5. Riepilogo Finale
    logger.info("--- Indicizzazione Completata ---")
    logger.info(f"Pagamenti totali nel CSV: {total_pagamenti}")
    # Calcola successo effettivo considerando i fallimenti
    successful_count = total_pagamenti - len(set(failed_pagamenti_indices))
    logger.info(f"Pagamenti processati con successo (almeno un chunk indicizzato): {successful_count}")
    if failed_pagamenti_indices:
        logger.warning(f"Pagamenti falliti (nessun chunk indicizzato a causa di errori embedding/upsert): {len(set(failed_pagamenti_indices))}")
        # Potresti loggare gli indici falliti se sono pochi:
        # logger.warning(f"Indici DataFrame falliti: {sorted(list(set(failed_pagamenti_indices)))}")
    logger.info(f"Elementi totali nella collezione ChromaDB '{collection.name}': {collection.count()}")

    return successful_count > 0 or total_pagamenti == 0 # Ritorna True se almeno uno è andato a buon fine o se non c'era nulla da fare

# --- Blocco Esecuzione ---
if __name__ == "__main__":
    start_time = time.time()
    success = index_pagamenti_to_chroma()
    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"Script terminato in {duration:.2f} secondi. Successo: {success}")
    if not success:
        exit(1) # Esce con codice di errore se fallito