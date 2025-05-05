import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Optional

import chromadb
import google.generativeai as genai
from dotenv import load_dotenv
from google.api_core import exceptions as google_exceptions

# --- Configurazione Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Caricamento Configurazione (Simile a index_pagamenti_chroma) ---
try:
    load_dotenv()
    # Recupera configurazioni essenziali per la query
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    CHROMA_DB_PATH = os.environ.get("CHROMA_DB_PATH", "data/database/chroma_db_pagamenti")
    CHROMA_COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION_NAME", "pagamenti_busto")
    GEMINI_EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")
    RAG_GENERATIVE_MODEL = os.environ.get("RAG_GENERATIVE_MODEL", "gemini-1.5-flash-latest")
    RAG_DEFAULT_N_RESULTS = int(os.environ.get("RAG_DEFAULT_N_RESULTS", 7))
    # RAG_REFERENCE_DISTANCE_THRESHOLD = float(os.environ.get("RAG_REFERENCE_DISTANCE_THRESHOLD", 0.75)) # Opzionale

    # Costruisci percorso ChromaDB
    PROJECT_ROOT = Path(__file__).parent.parent.resolve()
    chroma_db_full_path = PROJECT_ROOT / CHROMA_DB_PATH

    # Verifica configurazioni critiche
    if not GOOGLE_API_KEY: raise ValueError("GOOGLE_API_KEY non trovata nel file .env")
    if not os.path.exists(chroma_db_full_path):
        # Avvisa se il DB non esiste, ma non bloccare (potrebbe essere creato da indexer)
        logger.warning(f"Directory ChromaDB specificata ({chroma_db_full_path}) non esiste ancora.")
    # Configura API Google una sola volta qui
    genai.configure(api_key=GOOGLE_API_KEY)
    logger.info("Google GenAI configurato per RAG Query.")

except (ValueError, KeyError, TypeError) as e:
    logger.critical(f"Errore critico nella configurazione per RAG Query: {e}. Assicurati che .env esista.", exc_info=True)
    # Non usciamo, ma le funzioni potrebbero fallire se la config non è caricata
    genai = None # Impedisce chiamate se config fallita

# --- Costanti Embedding ---
TASK_TYPE_QUERY = "retrieval_query"

# --- Funzione Helper per Embedding Query (Potrebbe essere in un modulo utils) ---
def get_embedding_for_query(query: str) -> Optional[list[float]]:
    """Genera l'embedding per una singola query utente."""
    if not genai: # Se config fallita
        logger.error("Modulo GenAI non configurato correttamente.")
        return None
    if not query or not isinstance(query, str): return None
    try:
        result = genai.embed_content(
            model=GEMINI_EMBEDDING_MODEL,
            content=query,
            task_type=TASK_TYPE_QUERY
        )
        return result.get('embedding')
    except Exception as e:
        logger.error(f"Errore generazione embedding per query '{query[:50]}...': {e}", exc_info=True)
        return None

# --- Funzione Helper per Costruire il Prompt ---
def build_rag_prompt(query: str, context_chunks: list[dict], enrichment_context: Optional[str] = None) -> str:
    """Costruisce il prompt per l'LLM includendo il contesto recuperato e l'eventuale arricchimento."""
    looker_studio_link = "https://lookerstudio.google.com/u/0/reporting/13b653b0-06e4-44fa-9d33-b4f05a13ecef/page/hRYIF"

    # Gestione fallback invariata
    if not context_chunks and not enrichment_context: # Modifica: non fare fallback se hai almeno l'enrichment
        logger.warning("Nessun chunk di contesto RAG né arricchimento disponibile. Uso prompt di fallback standard.")
        # Qui potresti decidere se il fallback standard va bene o se vuoi un messaggio leggermente diverso
        # se hai solo l'enrichment ma non i pagamenti specifici. Per ora, manteniamo il fallback standard.
        prompt_fallback = f"""Sei un assistente AI specializzato sui dati di spesa del Comune di Busto Arsizio.
                    Le informazioni recuperate dai pagamenti analizzati non contengono una risposta diretta alla seguente domanda.
                    Domanda: {query}
                    Suggerimento: Puoi provare a esplorare i dati in modo più dettagliato utilizzando il cruscotto pubblico disponibile qui: {looker_studio_link}"""
        return prompt_fallback

    # Formatta il contesto dei pagamenti (solo se ci sono chunk)
    context_pagamenti_section = ""
    if context_chunks:
        context_pagamenti = "\n---\n".join([
            f"Info Pagamento (Anno: {chunk.get('metadata', {}).get('anno', 'N/A')}, "
            f"Beneficiario: {chunk.get('metadata', {}).get('beneficiario', 'N/A')}, "
            f"Importo: {chunk.get('metadata', {}).get('importo_str', 'N/A')}) "
            f"Descrizione: {chunk.get('document', '')}"
            for chunk in context_chunks
        ])
        context_pagamenti_section = f"""
**Contesto recuperato dai pagamenti:**
---
{context_pagamenti}
---
"""

    # 2. Prepara la sezione per l'arricchimento (solo se fornito)
    enrichment_section = ""
    if enrichment_context:
        enrichment_section = f"""
**Informazioni aggiuntive sul beneficiario (da Wikipedia):**
---
{enrichment_context}
---
"""

    # 4. Aggiorna le istruzioni e il prompt finale
    prompt = f"""Sei un assistente AI specializzato nell'analisi dei dati di spesa (pagamenti) del Comune di Busto Arsizio.
    Il tuo compito è rispondere alla domanda dell'utente basandoti **PRIMARIAMENTE** sulle informazioni presenti nel "Contesto recuperato dai pagamenti" e nelle "Informazioni aggiuntive sul beneficiario" (se presenti) qui sotto. Non usare conoscenze esterne se non specificamente richiesto.

    **Istruzioni:**
1. Leggi attentamente la "Domanda Utente".
2. Trova le informazioni rilevanti **principalmente** nel "Contesto recuperato dai pagamenti" e nelle "Informazioni aggiuntive".
3.  Formula una risposta concisa e precisa usando **SOLO** le informazioni trovate. Dai priorità ai dettagli specifici dei pagamenti, ma integra con le informazioni aggiuntive se aiutano a contestualizzare il beneficiario e a rispondere alla domanda.
4.  **FORMATTAZIONE IMPORTI MONETARI:** (Invariata - come la tua)
    *   Usa la **virgola (,)** come separatore decimale.
    *   Usa il **punto (.)** come separatore delle migliaia.
    *   Posiziona il simbolo "**€**" **dopo** il numero con uno spazio (es. **1.234,56 €**).
    *   Includi sempre due cifre decimali (es. **10,00 €**, **305,00 €**).
5.  **Non usare MAI la formattazione Markdown (come **grassetto** o *corsivo*) per gli importi monetari.**
6. Se il contesto fornito (pagamenti e/o Wikipedia) non contiene informazioni sufficienti per rispondere direttamente alla domanda:
    a. Se la domanda è una richiesta di informazioni generali su un ente menzionato (es. "Chi è [Ente]?", "Cosa fa [Ente]?"), **PUOI** usare la tua conoscenza generale per fornire una breve descrizione dell'ente, **specificando chiaramente che si tratta di informazioni generali non derivate dai dati di pagamento analizzati**.
    b. Altrimenti, se la domanda riguardava dettagli specifici dei pagamenti non trovati, rispondi ESATTAMENTE con: "Le informazioni recuperate dai pagamenti non contengono una risposta diretta a questa domanda specifica. Puoi provare a esplorare i dati più nel dettaglio qui: {looker_studio_link}"
7. Sii fedele ai dati forniti quando disponibili. Dai priorità alle informazioni specifiche dei pagamenti.

{enrichment_section} # <-- 3. Inserisci la sezione di arricchimento qui

{context_pagamenti_section} # <-- Inserisci la sezione dei pagamenti qui (potrebbe essere vuota se non ci sono chunk)

**Domanda Utente:** {query}

**Risposta (basata esclusivamente sul contesto fornito):**"""

    # logger.debug(f"Prompt costruito per LLM RAG:\n{prompt}")
    return prompt

# --- Funzione Principale di Query ---
def ask_pagamenti(query: str, n_results: int = RAG_DEFAULT_N_RESULTS) -> Dict:
    """
    Interroga la base di conoscenza dei pagamenti e genera una risposta RAG.

    Args:
        query: La domanda dell'utente in linguaggio naturale.
        n_results: Il numero di chunk rilevanti da recuperare da ChromaDB.

    Returns:
        Un dizionario contenente:
        - success (bool): True se la risposta è stata generata, False altrimenti.
        - answer (str | None): La risposta generata dall'LLM o un messaggio di errore/blocco.
        - references (list[dict]): Lista dei metadati dei chunk usati come contesto.
        - error_code (str | None): Codice di errore se success è False.
        - error_message (str | None): Messaggio di errore se success è False.
    """
    response_payload = {
        "success": False, "answer": None, "references": [],
        "error_code": None, "error_message": None
    }

    if not genai: # Se config iniziale fallita
        response_payload["error_code"] = "CONFIG_ERROR"
        response_payload["error_message"] = "Modulo Google GenAI non configurato."
        return response_payload

    # 1. Genera Embedding Query
    logger.info(f"Generazione embedding per query: '{query[:100]}...'")
    query_embedding = get_embedding_for_query(query)
    if not query_embedding:
        response_payload["error_code"] = "EMBEDDING_FAILED"
        response_payload["error_message"] = "Impossibile generare l'embedding per la query."
        return response_payload
    logger.info("Embedding query generato.")

    # 2. Connetti a ChromaDB e Query
    retrieved_chunks = []
    try:
        logger.debug(f"Connessione a ChromaDB: {chroma_db_full_path}")
        client = chromadb.PersistentClient(path=str(chroma_db_full_path))
        logger.debug(f"Ottenimento collezione: {CHROMA_COLLECTION_NAME}")
        collection = client.get_collection(name=CHROMA_COLLECTION_NAME) # Usa get_collection, deve esistere!

        logger.info(f"Esecuzione query vettoriale su '{collection.name}' (n_results={n_results})...")
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=['documents', 'metadatas', 'distances'] # Chiedi tutto
        )
        logger.info("Query ChromaDB completata.")

        # Estrai e formatta i risultati (già ordinati per distanza da ChromaDB)
      
# Estrai e formatta i risultati (già ordinati per distanza da ChromaDB)
        if results and results.get('ids', [[]])[0]: # Controlla se ci sono risultati
            ids = results['ids'][0]
            distances = results['distances'][0]
            metadatas = results['metadatas'][0]
            documents = results['documents'][0] # Testo dei chunk

            # --- INIZIO BLOCCO INDENTATO ---
            for id, dist, meta, doc in zip(ids, distances, metadatas, documents):
                # Aggiungi la distanza ai metadati che salviamo come riferimenti
                meta_with_distance = meta.copy()
                meta_with_distance['distance'] = dist
                meta_with_distance['retrieved_doc_text_preview'] = doc[:100] + "..."
                retrieved_chunks.append({
                    "id": id,
                    "distance": dist,
                    "metadata": meta,
                    "document": doc
                })
                response_payload["references"].append(meta_with_distance) # Popola con distanza
            # --- FINE BLOCCO INDENTATO ---

            logger.info(f"Recuperati {len(retrieved_chunks)} chunk rilevanti da ChromaDB.")
            if retrieved_chunks: logger.debug(f"Miglior chunk (dist={retrieved_chunks[0]['distance']:.4f}): ID={retrieved_chunks[0]['id']}")
        else:
            logger.warning("Nessun risultato trovato nella query a ChromaDB.")
            response_payload["references"] = [] # Assicura sia vuoto se non trova nulla

    

    except chromadb.exceptions.CollectionNotFoundError:
         logger.error(f"Collezione ChromaDB '{CHROMA_COLLECTION_NAME}' non trovata in '{chroma_db_full_path}'. Eseguire prima l'indicizzazione.")
         response_payload["error_code"] = "COLLECTION_NOT_FOUND"
         response_payload["error_message"] = f"La base di conoscenza '{CHROMA_COLLECTION_NAME}' non è stata trovata. Eseguire prima l'indicizzazione."
         return response_payload
    except Exception as e:
        logger.error(f"Errore durante query a ChromaDB: {e}", exc_info=True)
        response_payload["error_code"] = "VECTORDB_QUERY_FAILED"
        response_payload["error_message"] = f"Errore durante la ricerca nella base di conoscenza: {e}"
        return response_payload

    # 3. Prepara Prompt e Chiama LLM

    if not retrieved_chunks:
         # Se Chroma non ha trovato nulla, non chiamare l'LLM
         response_payload["answer"] = "Non ho trovato informazioni pertinenti nei dati dei pagamenti per rispondere alla tua domanda."
         response_payload["success"] = True # L'operazione è riuscita, anche se la risposta è vuota
         return response_payload

    logger.info("Costruzione prompt RAG...")
    prompt = build_rag_prompt(query, retrieved_chunks)

    logger.info(f"Chiamata al modello generativo: {RAG_GENERATIVE_MODEL}...")
    llm_answer = None
    block_reason = None
    try:
        model = genai.GenerativeModel(RAG_GENERATIVE_MODEL)
        # Potresti voler aggiungere generation_config e safety_settings qui se li definisci in .env
        # generation_config_dict = current_app.config.get('RAG_GENERATION_CONFIG', {}) # Se fossimo in Flask
        # safety_settings_dict = current_app.config.get('RAG_SAFETY_SETTINGS', None)   # Se fossimo in Flask
        response = model.generate_content(prompt) # , generation_config=..., safety_settings=...

        try:
            llm_answer = response.text
            logger.info("Risposta LLM generata.")
            response_payload["success"] = True
        except ValueError as e_block: # Risposta bloccata
            logger.warning(f"Risposta LLM bloccata per sicurezza: {e_block}")
            response_payload["success"] = False
            response_payload["error_code"] = 'GENERATION_BLOCKED'
            try: # Cerca di ottenere il motivo del blocco
                block_reason = response.prompt_feedback.block_reason.name
                response_payload["error_message"] = f"La risposta è stata bloccata per motivi di sicurezza ({block_reason})."
            except Exception:
                response_payload["error_message"] = "La risposta è stata bloccata per motivi di sicurezza (ragione sconosciuta)."
            llm_answer = None # Nessuna risposta testuale in questo caso
        except Exception as e_text: # Errore nell'accedere a response.text
             logger.error(f"Errore accesso a response.text: {e_text}", exc_info=True)
             response_payload["success"] = False
             response_payload["error_code"] = 'GENERATION_RESPONSE_ERROR'
             response_payload["error_message"] = f"Errore nell'ottenere il testo dalla risposta LLM: {e_text}"
             llm_answer = None

    except google_exceptions.ResourceExhausted as e_rate_llm:
        logger.error(f"Rate limit API LLM: {e_rate_llm}")
        response_payload["error_code"] = 'API_RATE_LIMIT_GENERATION'
        response_payload["error_message"] = 'Limite richieste API superato durante generazione risposta.'
    except google_exceptions.GoogleAPIError as e_google_api_llm:
        logger.error(f"Errore API Google LLM (Codice: {e_google_api_llm.code}): {e_google_api_llm}")
        response_payload["error_code"] = 'API_ERROR_GENERATION'
        response_payload["error_message"] = f'Errore API Google ({e_google_api_llm.code}) durante generazione risposta.'
    except Exception as llm_err:
        logger.error(f"Errore imprevisto chiamata LLM: {llm_err}", exc_info=True)
        response_payload["error_code"] = 'LLM_GENERATION_FAILED'
        response_payload["error_message"] = f'Errore imprevisto durante generazione risposta: {llm_err}'

    response_payload["answer"] = llm_answer
    return response_payload

# --- Blocco Esecuzione Test (Opzionale) ---
if __name__ == '__main__':
    logger.info("--- Test Modulo RAG Query ---")

    test_queries = [
        "Quali sono state le spese principali per manutenzione strade nel 2022?",
        "Ci sono pagamenti relativi a consulenze legali?",
        "Quanto si è speso per l'illuminazione pubblica nel 2023?",
        "Chi è il beneficiario AGESP?",
        "Sono stati fatti pagamenti per feste di Natale?",
        "Qual è il destinatario con il maggior numero di commissioni e importo totale commissionato?",
        "Qual è l'importo commissionato più alto?",
        "Sarebbe interessante capire per cosa si spendono i soldi, sapresti farmi 5 cateogira, ad esempio per il 2023?"
    ]

    for q in test_queries:
        print(f"\n--- DOMANDA: {q} ---")
        start_q = time.time()
        result = ask_pagamenti(q) # result ora contiene response_payload
        end_q = time.time()
        print(f"  >> Tempo Esecuzione: {end_q - start_q:.2f} secondi")
        print(f"  Successo: {result['success']}")

        if result['success']:
            print(f"  Risposta: {result['answer']}")
        else:
            print(f"  Errore ({result['error_code']}): {result['error_message']}")

        # --- INIZIO BLOCCO STAMPA CORRETTO ---
        references_list = result.get('references', []) # Prendi la lista dal risultato
        print(f"  Riferimenti ({len(references_list)}):")
        if references_list:
            # Itera sui primi N riferimenti (es. 5) dalla lista restituita
            for i, ref_data in enumerate(references_list[:5]):
                # Estrai i dati dal dizionario del riferimento
                # ref_data contiene i metadati PIÙ la chiave 'distance' che abbiamo aggiunto
                dist = ref_data.get('distance', -1.0) # Ottieni la distanza
                anno = ref_data.get('anno', 'N/A')
                benef = ref_data.get('beneficiario', 'N/A')
                importo = ref_data.get('importo_str', 'N/A')
                preview = ref_data.get('retrieved_doc_text_preview', '') # Prendi la preview
                
                # --- INIZIO FORMATTAZIONE IMPORTO ---
                importo_str_formatted = "N/A"
                # Prova a prendere il float se esiste (lo aggiungeremo nei metadati dell'indexer)
                # Altrimenti usa la stringa originale
                importo_val = ref_data.get('importo_float', ref_data.get('importo_str'))

                if importo_val is not None:
                    try:
                        # Converti in float (potrebbe essere già float o stringa da convertire)
                        importo_f = float(str(importo_val).replace(',', '.')) # Assicura punto decimale per formattazione
                        # Formatta con separatore migliaia '.' e decimale ','
                        importo_str_formatted = "{:,.2f}".format(importo_f).replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
                    except (ValueError, TypeError):
                        # Se la conversione fallisce, usa la stringa originale se disponibile
                        importo_str_formatted = str(ref_data.get('importo_str', 'N/A'))

                # Stampa includendo la distanza
                print(f"    - Ref {i+1} (Dist: {dist:.4f}): Anno={anno}, Benef={benef}, Importo={importo} [{preview}]") # Aggiunta preview testo
        else:
            print("    Nessun riferimento recuperato.")
        # --- FINE BLOCCO STAMPA CORRETTO ---

        print("-" * 20)

    logger.info("--- Test Modulo RAG Query Completato ---")