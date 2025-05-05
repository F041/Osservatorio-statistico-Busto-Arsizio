# src/app.py

import logging
import os
import json
import time
import re
import sqlite3 # Assicurati sia importato
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from flask import redirect, url_for 
from flask_cors import CORS
from dotenv import load_dotenv
from cachetools import LRUCache # `cached` non è usato
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
#from flask_babelex import Babel

# Import robusti dei moduli locali
try:
    from .rag_query import get_embedding_for_query, build_rag_prompt, RAG_GENERATIVE_MODEL
    from .tools.sql_aggregator_tool import (
        get_total_spend_beneficiary_year,
        find_official_beneficiary_name,
        get_top_suppliers_by_year,
        get_payment_count_beneficiary_year
    )
    # Import normalize_string
    from .tools.wikipedia_enricher_tool import normalize_string
except ImportError:
    import sys
    # Aggiungi la directory 'src' al path se necessario per trovare i moduli
    # Utile se esegui `python src/app.py` dalla root
    current_dir = Path(__file__).parent.resolve()
    if str(current_dir) not in sys.path:
        sys.path.append(str(current_dir))
    # Aggiungi anche la root del progetto al path
    project_root_dir = current_dir.parent
    if str(project_root_dir) not in sys.path:
        sys.path.append(str(project_root_dir))

    try:
        # Prova di nuovo l'import relativo dalla directory corrente (src)
        from rag_query import get_embedding_for_query, build_rag_prompt, RAG_GENERATIVE_MODEL
        from tools.sql_aggregator_tool import (
            get_total_spend_beneficiary_year,
            find_official_beneficiary_name,
            get_top_suppliers_by_year,
            get_payment_count_beneficiary_year
        )
        from tools.wikipedia_enricher_tool import normalize_string
    except ImportError as e:
        logging.critical(f"Errore critico: Impossibile importare moduli backend. Dettagli: {e}", exc_info=True)
        # Definisci una funzione dummy per normalize_string per evitare errori successivi se l'import fallisce
        def normalize_string(s):
            logging.error("normalize_string non importata, usando fallback!")
            return str(s).lower().strip() if s else ""
        # Potresti voler uscire qui se moduli critici non vengono caricati
        # sys.exit(1)

import chromadb
import google.generativeai as genai
import google.api_core.exceptions

# --- Configurazione Iniziale ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configura Google GenAI
try:
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    if not GOOGLE_API_KEY: raise ValueError("GOOGLE_API_KEY non trovata nel file .env")
    genai.configure(api_key=GOOGLE_API_KEY)
    logger.info("Google GenAI configurato per Flask app.")
except Exception as e:
    logger.critical(f"Fallimento configurazione Google Generative AI in app.py: {e}", exc_info=True)
    genai = None # Impedisce chiamate se fallisce

# --- Configurazione Percorsi e App Flask ---
script_dir = Path(__file__).parent.resolve()
app = Flask(__name__,
            static_folder=str(script_dir / 'static'),
            template_folder=str(script_dir / 'templates'))

# --- Configurazione CORS ---
origins_allowed = os.environ.get("ALLOWED_ORIGINS", "*").split(',') # Leggi da .env, default a "*"
if origins_allowed == ["*"]:
     logger.warning("CORS configurato per permettere TUTTE le origini ('*'). Modificare ALLOWED_ORIGINS in .env per produzione.")
CORS(app, resources={
    r"/ask": {"origins": origins_allowed},
    r"/widget": {"origins": origins_allowed},
    r"/embed.js": {"origins": origins_allowed}, # Permetti anche per embed.js
    # Considera se servire static/ da CORS se necessario
    # r"/static/*": {"origins": origins_allowed}
})

# --- Configurazione Caching ---
query_cache = LRUCache(maxsize=int(os.environ.get("QUERY_CACHE_SIZE", 128)))

# --- Funzione Helper formato SSE ---
def format_sse(data: dict, event: str = 'message') -> str:
    """Formatta dati come evento Server-Sent."""
    json_data = json.dumps(data)
    return f"event: {event}\ndata: {json_data}\n\n"

# --- NUOVA SEZIONE: Configurazione Flask-Admin ---

# 1. Configura SQLAlchemy per puntare al DB SQLite esistente
#    Assicurati che DB_PATH sia definito correttamente prima di questa sezione
#    (lo prendiamo da sql_aggregator_tool o lo ridefiniamo qui)
try:
    PROJECT_ROOT_FA = Path(__file__).parent.parent.resolve()
    DB_ENV_VAR_FA = os.environ.get("DATABASE_FILE", "data/database/busto_pagamenti.db")
    DB_PATH_FA = PROJECT_ROOT_FA / DB_ENV_VAR_FA
    if not DB_PATH_FA.is_file():
        raise FileNotFoundError(f"Database non trovato per Flask-Admin: {DB_PATH_FA}")
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH_FA.resolve()}' # Usa path assoluto per sicurezza
    logger.info(f"Configurazione SQLAlchemy per Flask-Admin: {SQLALCHEMY_DATABASE_URI}")
except Exception as e_db_fa:
    logger.critical(f"Errore configurazione DB per Flask-Admin: {e_db_fa}", exc_info=True)
    # Potresti voler uscire se il DB non è configurabile
    SQLALCHEMY_DATABASE_URI = None # Impedisce l'avvio di SQLAlchemy se fallisce

if SQLALCHEMY_DATABASE_URI:
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
    # --- NUOVE CONFIGURAZIONI BABEL ---
    #app.config['BABEL_DEFAULT_LOCALE'] = 'it' # Imposta italiano come lingua predefinita
    #app.config['BABEL_DEFAULT_TIMEZONE'] = 'Europe/Rome' # Imposta fuso orario
    #babel = Babel(app) # Inizializza Babel con l'app
    # -----------------------------------

    db_flaskadmin = SQLAlchemy(app)

    # 2. Definisci Classi Modello per le Tabelle Esistenti
    #    Queste classi dicono a Flask-Admin/SQLAlchemy come interagire con le tabelle.
    #    Non devono necessariamente mappare OGNI colonna se non fai ORM completo.
    #    È importante definire __tablename__ e una primary_key (anche 'rowid').

    class Pagamenti(db_flaskadmin.Model):
        __tablename__ = 'pagamenti'
        # Usa 'rowid' come chiave primaria surrogata per SQLite se non ne hai una definita
        # Questo permette a Flask-Admin di identificare univocamente le righe.
        rowid = db_flaskadmin.Column('rowid', db_flaskadmin.Integer, primary_key=True)
        # Definisci esplicitamente le colonne che vuoi rendere ricercabili/filtrabili/visibili
        # per un controllo migliore (opzionale, ma buona pratica)
        NumeroMandato = db_flaskadmin.Column(db_flaskadmin.Integer)
        Anno = db_flaskadmin.Column(db_flaskadmin.Integer)
        DataMandato = db_flaskadmin.Column(db_flaskadmin.TIMESTAMP)
        CIG = db_flaskadmin.Column(db_flaskadmin.Text)
        Beneficiario = db_flaskadmin.Column(db_flaskadmin.Text)
        ImportoEuro = db_flaskadmin.Column(db_flaskadmin.REAL)
        DescrizioneMandato = db_flaskadmin.Column(db_flaskadmin.Text)
        NomeFileOrigine = db_flaskadmin.Column(db_flaskadmin.Text)

    class BeneficiariInfo(db_flaskadmin.Model):
        __tablename__ = 'beneficiari_info'
        rowid = db_flaskadmin.Column('rowid', db_flaskadmin.Integer, primary_key=True)
        # Definisci colonne
        Beneficiario = db_flaskadmin.Column(db_flaskadmin.Text)
        NomeNormalizzato = db_flaskadmin.Column(db_flaskadmin.Text)
        NomeUsatoPerRicerca = db_flaskadmin.Column(db_flaskadmin.Text)
        LookupStatus = db_flaskadmin.Column(db_flaskadmin.Text)
        WikipediaURL = db_flaskadmin.Column(db_flaskadmin.Text)
        WikipediaSummary = db_flaskadmin.Column(db_flaskadmin.Text)


    # 3. Crea Viste Personalizzate per Flask-Admin (per sola lettura)
    class ReadOnlyModelView(ModelView):
        """Vista base per sola lettura."""
        can_create = False
        can_edit = False
        can_delete = False
        page_size = 50 # Numero di righe per pagina

    class PagamentiAdminView(ReadOnlyModelView):
        column_list = ['Anno', 'DataMandato', 'Beneficiario', 'ImportoEuro', 'DescrizioneMandato', 'CIG', 'NumeroMandato'] # Colonne da mostrare e ordine
        column_searchable_list = ['Beneficiario', 'DescrizioneMandato', 'CIG', 'NumeroMandato'] # Ricerca testuale
        column_filters = ['Anno', 'Beneficiario'] # Filtri dropdown/input
        column_labels = {'ImportoEuro': 'Importo (€)', 'DataMandato': 'Data', 'DescrizioneMandato': 'Descrizione'} # Etichette più leggibili
        column_formatters = { # Formattazione colonne
           'ImportoEuro': lambda v, c, m, p: f"{m.ImportoEuro:,.2f} €".replace(",", "#").replace(".", ",").replace("#", ".") if m.ImportoEuro is not None else "",
           'DataMandato': lambda v, c, m, p: m.DataMandato.strftime('%Y-%m-%d') if m.DataMandato else ''
        }
        column_default_sort = ('DataMandato', True) # Ordina per data discendente di default
    # --- Inizializzazione Admin  ---
    # 1. Crea l'istanza della vista che sarà l'indice
    #    Assegniamo un endpoint esplicito per chiarezza, anche se non strettamente necessario
    #    quando è l'unica vista e l'index_view.
    pagamenti_index_view = PagamentiAdminView(Pagamenti, db_flaskadmin.session,
                                             name='Pagamenti', # Nome visualizzato se ci fosse un menu
                                             endpoint='pagamenti' # Endpoint base per questa vista
                                             # Non serve specificare 'url' qui
                                            )

    # 2. Inizializza Admin passando l'istanza come index_view
    admin = Admin(app,
                name='Osservatorio Pagamenti',
                url='/esplora-dati', 
                template_mode='bootstrap4',
                #base_template='base.html' 
                )

    # Aggiungi la vista Pagamenti. L'endpoint di default sarà 'pagamenti'.
    admin.add_view(PagamentiAdminView(Pagamenti, db_flaskadmin.session,
                                      name='Tabella Completa', # Nome nel menu di Admin (se visibile)
                                      endpoint='pagamenti' # Esplicito per url_for
                                      ))

    logger.info(f"Flask-Admin configurato su {admin.url} usando base_template.")
else:
    logger.error("Flask-Admin non disponibile.")

@app.route('/')
def index():
    # Serve la pagina della chat (che eredita da base.html)
    logger.info("Accesso alla pagina index (Chat AI).")
    return render_template('index.html')

@app.route('/widget')
def widget_content():
    """Renderizza l'HTML specifico per l'iframe del widget."""
    logger.info("Richiesta per /widget (contenuto iframe).")
    return render_template('widget.html')

@app.route('/embed.js')
def serve_embed_js():
    """Serve lo script embed.js."""
    logger.debug("Richiesta per /embed.js")
    # Assumendo che embed.js sia nella cartella static/js/
    static_dir = app.static_folder
    # Verifica se static_dir è una stringa o un Path e costruisci il percorso
    if isinstance(static_dir, str):
        embed_js_path = Path(static_dir) / 'js'
    elif isinstance(static_dir, Path):
        embed_js_path = static_dir / 'js'
    else:
        logger.error("app.static_folder non è né stringa né Path.")
        return "Internal Server Error", 500
    # Assicurati che il percorso esista prima di inviare
    if not (embed_js_path / 'embed.js').is_file():
        logger.error(f"File embed.js non trovato in {embed_js_path}")
        return "Not Found", 404
    return send_from_directory(embed_js_path, 'embed.js', mimetype='application/javascript')


# **** FUNZIONE GENERATORE SPOSTATA FUORI DALLA ROUTE ****
def stream_query_response(user_query: str, query_key_for_cache: str):
    """
    Generatore che produce eventi SSE per la risposta alla query.
    Accetta query_key per il caching.
    """
    final_payload = {"success": False, "answer": None, "references": [], "table_data": None, "error_code": None, "error_message": None}
    intent = "rag"
    sql_params = {}
    run_rag_anyway = False

    # --- Blocco Try-Except Esterno ---
    try:
        # --- 1. RICONOSCIMENTO INTENTO ---
        query_lower = user_query.lower()
        yield format_sse({"status": "Analisi della domanda in corso..."}, event='status')

        match_spend_beneficiary_year = re.search(r"quanto(?:\s+si\s+è)?\s+speso\s+(?:per|a)\s+(.+)\s+nel\s+(\d{4})\??$", query_lower)
        match_top_suppliers_year = re.search(
            r"^\s*(?:chi sono i|quali sono i|top|principali)\s+(?:beneficiari|fornitori)(?:\s+nel)?\s+(\d{4})\??\s*$",
            query_lower
        )
        match_count_beneficiary_year = re.search(r"(?:quanti|numero)\s+pagamenti\s+(?:ha\s+)?(?:ricevuto|per)\s+(.+)\s+(?:nel|nell'anno)\s+(\d{4})\??$", query_lower)

        if match_spend_beneficiary_year:
            potential_beneficiary = match_spend_beneficiary_year.group(1).strip()
            potential_year = match_spend_beneficiary_year.group(2).strip()
            yield format_sse({"status": f"Verifica beneficiario '{potential_beneficiary}'..."}, event='status')
            official_beneficiary_name = find_official_beneficiary_name(potential_beneficiary)
            if official_beneficiary_name:
                intent = "sql_total_spend_beneficiary_year"; sql_params = {'beneficiary_name': official_beneficiary_name, 'year': potential_year}
                logger.info(f"Intent: {intent}, Params: {sql_params}")
            else: intent = "rag"; logger.info("Lookup fallita, fallback a RAG.")
        elif match_top_suppliers_year:
            intent = "sql_top_suppliers_year"; sql_params = {'year': match_top_suppliers_year.group(1).strip(), 'top_n': 5}
            yield format_sse({"status": f"Riconosciuto: Ricerca fornitori principali per l'anno {sql_params.get('year','N/A')}..."}, event='status')
            logger.info(f"Intent: {intent}, Params: {sql_params}")
        elif match_count_beneficiary_year:
            potential_beneficiary_count = match_count_beneficiary_year.group(1).strip()
            potential_year_count = match_count_beneficiary_year.group(2).strip()
            yield format_sse({"status": f"Verifica beneficiario '{potential_beneficiary_count}'..."}, event='status')
            official_beneficiary_name_count = find_official_beneficiary_name(potential_beneficiary_count)
            if official_beneficiary_name_count:
                intent = "sql_payment_count_beneficiary_year"; sql_params = {'beneficiary_name': official_beneficiary_name_count, 'year': potential_year_count}
                logger.info(f"Intent: {intent}, Params: {sql_params}")
            else: intent = "rag"; logger.info("Lookup fallita, fallback a RAG.")
        else:
            intent = "rag"; logger.info("Nessun intento SQL specifico. Procedo con RAG.")
            yield format_sse({"status": "Riconosciuto: Ricerca informazioni generali (RAG)..."}, event='status')

        # --- 2. ESECUZIONE LOGICA INTENTO ---

        if intent == "sql_total_spend_beneficiary_year":
            beneficiary_to_query = sql_params['beneficiary_name']; year_to_query = sql_params['year']
            yield format_sse({"status": f"Eseguo query SQL per spesa totale ('{beneficiary_to_query}' - {year_to_query})..."}, event='status')
            sql_result = get_total_spend_beneficiary_year(beneficiary_to_query, year_to_query)
            if sql_result:
                amount_formatted = "{:,.2f}".format(sql_result['total_amount']).replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
                final_payload.update({
                    "success": True, "answer": f"Nel {sql_result['year']}, la spesa totale registrata per '{sql_result['beneficiary']}' ammonta a {amount_formatted} €, basata su {sql_result['record_count']} pagamenti.",
                    "table_data": [{"Anno": sql_result['year'], "Beneficiario": sql_result['beneficiary'], "Importo Totale": sql_result['total_amount'], "N. Record": sql_result['record_count']}], "references": []
                })
                logger.info("Payload impostato da SQL: Totale Spesa OK.")
            else:
                logger.info(f"Query SQL per '{beneficiary_to_query}' anno {year_to_query} non ha prodotto risultati. Fallback a RAG.")
                intent = "rag"; run_rag_anyway = True
                yield format_sse({"status": "Nessun totale trovato. Avvio ricerca generica..."}, event='status')

        elif intent == "sql_top_suppliers_year":
             year_to_query = sql_params['year']; top_n_query = sql_params['top_n']
             yield format_sse({"status": f"Eseguo query SQL per top {top_n_query} fornitori ({year_to_query})..."}, event='status')
             sql_results_list = get_top_suppliers_by_year(year_to_query, top_n_query)
             if sql_results_list is not None:
                 if sql_results_list:
                     final_payload.update({"success": True, "answer": f"Ecco i principali {len(sql_results_list)} fornitori registrati nel {year_to_query} in base agli importi totali:",
                                           "table_data": [{"Pos.": i+1, "Fornitore": r["Beneficiario"], "Importo Totale": r["TotaleSpeso"]} for i, r in enumerate(sql_results_list)], "references": []})
                     logger.info("Payload impostato da SQL: Top Fornitori OK.")
                 else:
                     final_payload.update({"success": True, "answer": f"Non ho trovato fornitori con pagamenti registrati per l'anno {year_to_query}.", "references": [], "table_data": None })
                     logger.info("Payload impostato da SQL: Top Fornitori (Nessuno Trovato).")
             else:
                  final_payload.update({ "success": False, "answer": f"Si è verificato un errore nel recuperare i fornitori principali per l'anno {year_to_query}.", "error_code": "SQL_EXECUTION_ERROR", "error_message": "Errore DB durante query top suppliers.", "references": [], "table_data": None })
                  logger.error("Errore SQL Top Fornitori, payload errore impostato.")

        elif intent == "sql_payment_count_beneficiary_year":
             beneficiary_to_query = sql_params['beneficiary_name']; year_to_query = sql_params['year']
             yield format_sse({"status": f"Eseguo query SQL per conteggio pagamenti ('{beneficiary_to_query}' - {year_to_query})..."}, event='status')
             sql_result = get_payment_count_beneficiary_year(beneficiary_to_query, year_to_query)
             if sql_result is not None:
                 record_count = sql_result['record_count']
                 answer_text = f"Nel {sql_result['year']}, risultano registrati {record_count} pagamenti per '{sql_result['beneficiary']}'." if record_count > 0 else f"Nel {sql_result['year']}, non risultano pagamenti registrati per '{sql_result['beneficiary']}'."
                 final_payload.update({ "success": True, "answer": answer_text, "table_data": [{"Anno": sql_result['year'], "Beneficiario": sql_result['beneficiary'], "Numero Pagamenti": record_count}], "references": [] })
                 logger.info("Payload impostato da SQL: Conteggio Pagamenti OK.")
             else:
                 logger.error(f"Errore SQL durante il conteggio pagamenti per '{beneficiary_to_query}', anno {year_to_query}.")
                 final_payload.update({ "success": False, "answer": f"Errore conteggio pagamenti per '{beneficiary_to_query}' anno {year_to_query}.", "error_code": "SQL_EXECUTION_ERROR", "error_message": "Errore DB durante query di conteggio.", "references": [], "table_data": None })
                 logger.error("Errore SQL Conteggio Pagamenti, payload errore impostato.")

        # --- Blocco Intent RAG ---
        else:
            if intent != 'rag': raise Exception(f"Errore logico intent: {intent}")
            logger.info("Esecuzione blocco RAG...")
            retrieved_chunks = []
            references_for_payload = []
            enrichment_summary = None
            if not run_rag_anyway: yield format_sse({"status": "Preparazione ricerca semantica..."}, event='status')
            try: # ChromaDB & Embedding
                yield format_sse({"status": "Calcolo rappresentazione semantica..."}, event='status')
                query_embedding = get_embedding_for_query(user_query)
                if not query_embedding: raise ValueError("Embedding failed")
                yield format_sse({"status": "Ricerca documenti simili..."}, event='status')
                PROJECT_ROOT=Path(__file__).parent.parent.resolve()
                chroma_db_full_path=PROJECT_ROOT/os.environ.get("CHROMA_DB_PATH", "data/database/chroma_db_pagamenti")
                client=chromadb.PersistentClient(path=str(chroma_db_full_path))
                collection_name=os.environ.get("CHROMA_COLLECTION_NAME", "pagamenti_busto")
                collection=client.get_collection(name=collection_name)
                n_results=int(os.environ.get("RAG_DEFAULT_N_RESULTS", 15))
                results=collection.query(query_embeddings=[query_embedding],n_results=n_results,include=['documents','metadatas','distances'])
                if results and results.get('ids',[[]])[0]:
                    ids=results['ids'][0]; distances=results['distances'][0]; metadatas=results['metadatas'][0]; documents=results['documents'][0];
                    for id, dist, meta, doc in zip(ids,distances,metadatas,documents):
                        retrieved_chunks.append({"id":id,"distance":dist,"metadata":meta,"document":doc})
                        meta_with_distance = meta.copy(); meta_with_distance['distance'] = dist; meta_with_distance['retrieved_doc_text_preview'] = doc[:150]+"..."; references_for_payload.append(meta_with_distance)
                    logger.info(f"Recuperati {len(retrieved_chunks)} chunk RAG.")
                else:
                    logger.warning("Nessun risultato query ChromaDB.")
                    retrieved_chunks = []
            except ValueError as e_val:
                logger.error(f"Errore embedding RAG: {e_val}")
                final_payload.update({"success": False, "answer": "Errore analisi domanda.", "error_code": "EMBEDDING_ERROR"})
            except Exception as e_chroma:
                error_message = str(e_chroma)
                logger.error(f"Errore ChromaDB RAG: {error_message}", exc_info=True)
                err_code = "COLLECTION_NOT_FOUND" if f"Collection {collection_name} not found" in error_message else "VECTORDB_QUERY_FAILED"
                err_answer = "Base di conoscenza non trovata." if err_code == "COLLECTION_NOT_FOUND" else f"Errore ricerca dati: {error_message}"
                final_payload.update({"success": False, "answer": err_answer, "error_code": err_code})

            # --- Arricchimento e LLM ---
            if final_payload.get('error_code') is None: # Procedi solo se non ci sono stati errori prima
                if retrieved_chunks:
                    potential_beneficiary_from_rag = None
                    if retrieved_chunks[0].get('metadata', {}).get('beneficiario'): potential_beneficiary_from_rag = retrieved_chunks[0]['metadata']['beneficiario']
                    if potential_beneficiary_from_rag:
                        # --- Logica Arricchimento ---
                        logger.info(f"Tentativo arricchimento per: '{potential_beneficiary_from_rag}'")
                        normalized_beneficiary_for_lookup = normalize_string(potential_beneficiary_from_rag)
                        if normalized_beneficiary_for_lookup:
                            conn_enrich=None
                            try:
                                PROJECT_ROOT_APP = Path(__file__).parent.parent.resolve(); DB_ENV_VAR_APP = os.environ.get("DATABASE_FILE", "data/database/busto_pagamenti.db"); DB_PATH_APP = PROJECT_ROOT_APP / DB_ENV_VAR_APP
                                if DB_PATH_APP and DB_PATH_APP.exists():
                                    conn_enrich = sqlite3.connect(DB_PATH_APP); cursor_enrich = conn_enrich.cursor(); query_enrich = "SELECT WikipediaSummary FROM beneficiari_info WHERE NomeNormalizzato = ? AND LookupStatus = 'found' LIMIT 1"; cursor_enrich.execute(query_enrich, (normalized_beneficiary_for_lookup,)); result_enrich = cursor_enrich.fetchone()
                                    if result_enrich and result_enrich[0]: enrichment_summary = result_enrich[0]; logger.info("Trovato riassunto.")
                            except Exception as e_enrich: logger.error(f"Errore lookup arricchimento: {e_enrich}")
                            finally:
                                if conn_enrich: conn_enrich.close()
                        # --- Fine Logica Arricchimento ---

                    # --- Chiamata LLM ---
                    yield format_sse({"status": "Invio informazioni all'intelligenza artificiale..."}, event='status')
                    prompt = build_rag_prompt(user_query, retrieved_chunks, enrichment_context=enrichment_summary)
                    yield format_sse({"status": "Attendo risposta dall'AI..."}, event='status')
                    try:
                        if not genai: raise Exception("Modulo GenAI non inizializzato")
                        llm_model=genai.GenerativeModel(RAG_GENERATIVE_MODEL)
                        llm_response=llm_model.generate_content(prompt)
                        try:
                            final_payload.update({"success": True, "answer": llm_response.text, "references": references_for_payload})
                            logger.info("Payload impostato da RAG: LLM OK.")
                        except ValueError as e_block:
                            block_reason=llm_response.prompt_feedback.block_reason.name if llm_response.prompt_feedback else 'UNKNOWN'
                            final_payload.update({"success": False, "answer": f"Risposta bloccata ({block_reason}).", "error_code": 'GENERATION_BLOCKED', "references": references_for_payload})
                            logger.warning(f"Blocco LLM RAG ({block_reason}).")
                        except Exception as e_text:
                            final_payload.update({"success": False, "answer": "Errore lettura LLM.", "error_code": 'GENERATION_RESPONSE_ERROR', "references": references_for_payload})
                            logger.error(f"Errore accesso testo LLM RAG: {e_text}.")
                    except Exception as llm_err:
                        final_payload.update({"success": False, "answer": "Errore generazione.", "error_code": 'LLM_GENERATION_FAILED', "references": references_for_payload})
                        logger.error(f"Errore API LLM RAG: {llm_err}.")
                    # --- Fine Chiamata LLM ---

                else: # Nessun chunk RAG
                    logger.warning("Nessun chunk RAG, imposto fallback.")
                    looker_studio_link = os.environ.get("LOOKER_STUDIO_LINK", "#")
                    answer_text = f"Non ho trovato informazioni specifiche nei pagamenti per rispondere a questa domanda. Puoi consultare il <a href='{looker_studio_link}' target='_blank'>cruscotto</a>."
                    final_payload.update({ "success": True, "answer": answer_text, "references": [], "table_data": None })
                    logger.info("Payload impostato da RAG: Nessun chunk trovato.")
            # --- Fine del blocco 'if final_payload.get('error_code') is None:' ---
        # --- Fine del blocco RAG (else) ---

    # --- Blocco Except Esterno ---
    except Exception as e_outer:
        logger.error(f"ERRORE NON GESTITO nel generatore 'stream_query_response': {e_outer}", exc_info=True)
        if final_payload.get('error_code') is None:
             final_payload.update({
                 "success": False, "answer": "Si è verificato un errore interno imprevisto.",
                 "references": [], "table_data": None, "error_code": "UNHANDLED_GENERATOR_ERROR",
                 "error_message": str(e_outer)
            })

    # --- Caching (Eseguito alla fine del generatore) ---
    if final_payload.get('success') and not final_payload.get('error_code'):
        try:
            # Assumiamo che query_cache sia globale e accessibile
            query_cache[query_key_for_cache] = final_payload # Usa la chiave passata
            logger.info(f"Risultato per query '{query_key_for_cache}' salvato nella cache.")
        except Exception as e_cache:
            logger.warning(f"Errore salvataggio cache: {e_cache}")

    # --- Yield Finale ---
    yield format_sse({"status": "Completato."}, event='status')
    time.sleep(0.1)
    yield format_sse(final_payload, event='result')
    logger.info(f"Generatore per query '{user_query[:50]}...' terminato, yield finale inviato.")


# --- ROUTE /ask CHE USA IL GENERATORE ESTERNO ---
@app.route('/ask', methods=['POST'])
def handle_ask_stream():
    # Controlli iniziali richiesta
    if not request.is_json:
        logger.warning("Richiesta non JSON.")
        return jsonify({"success": False, "answer": "Richiesta non valida.", "error_code": "BAD_REQUEST"}), 415
    data = request.get_json()
    user_query = data.get('query')
    if not user_query or not isinstance(user_query, str) or user_query.strip() == "":
        logger.warning("Query vuota.")
        return jsonify({"success": False, "answer": "Domanda vuota.", "error_code": "EMPTY_QUERY"}), 400
    logger.info(f"Richiesta /ask: '{user_query[:100]}...'")

    # Caching Check
    query_key = user_query.strip().lower()
    if query_key in query_cache:
        logger.info(f"Cache hit per: '{query_key}'")
        return jsonify(query_cache[query_key])

    # Crea e ritorna la risposta SSE
    # Passa user_query e query_key al generatore
    response = Response(stream_query_response(user_query, query_key), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

# --- Avvio App ---
if __name__ == '__main__':
    logger.info("Avvio server Flask...")
    app.run(debug=True, host='127.0.0.1', port=5000)