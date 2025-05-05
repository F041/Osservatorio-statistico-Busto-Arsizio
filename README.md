# Osservatorio Statistico Busto Arsizio

Questo progetto mira a creare un'interfaccia web (simile a un chatbot) per esplorare e interrogare dati pubblici relativi ai pagamenti del Comune di Busto Arsizio, combinando ricerca semantica (RAG) e query strutturate (SQL).

## Obiettivi (Stato Attuale)

*   ✅ **FASE 1 (Scraping): COMPLETATA**
    *   Scaricati automaticamente i file Excel/ODS/XLS dei pagamenti dalla sezione Trasparenza del sito comunale (`src/scraper.py`).
*   ✅ **FASE 2 (ETL): COMPLETATA**
    *   Puliti, trasformati e uniti i dati scaricati in un file CSV (`data/processed_data/processed_pagamenti.csv`) tramite `src/etl_processor.py`.
*   ✅ **FASE 3 (Storage): COMPLETATA**
    *   Salvati i dati puliti in un database SQLite (`data/database/busto_pagamenti.db`) tramite `src/load_to_sqlite.py`.
*   ✅ **FASE 4 (Frontend): COMPLETATA (Miglioramenti UX)**
    *   Sviluppata un'interfaccia web stile chat con **Flask** (`src/app.py`, `templates/`, `static/`) che:
        *   Permette all'utente di inviare domande in linguaggio naturale.
        *   Visualizza le risposte generate dal backend (testo, tabelle).
        *   ✅ Mostra i riferimenti RAG in modo espandibile.
        *   Implementa lo shortcut Ctrl+Invio per l'invio.
        *   ✅ Fornisce feedback sullo stato di elaborazione tramite Server-Sent Events (SSE) **migliorati e più descrittivi**.
        *   ✅ **Layout con Sidebar:** Implementato layout generale con sidebar di navigazione (`templates/base.html`) per separare la chat dall'esplorazione dati.
        *   ✅ **Suggerimenti Domande:** Aggiunti prompt starter cliccabili sopra l'area di input per guidare l'utente.
    *   ✅ **Widget Embeddabile:** Creata funzionalità per incorporare la chat su siti terzi tramite un semplice snippet JavaScript (`/embed.js`, `/widget`).
    *   ✅ **Esplorazione Dati Base:** Integrata interfaccia **Flask-Admin** (su `/esplora-dati`) per visualizzare, filtrare e cercare le tabelle `pagamenti` e `beneficiari_info` del database SQLite (configurazione iniziale, in attesa di traduzione/finalizzazione).

*   🚧 **FASE 5 (AI & Tools): IMPLEMENTAZIONE BASE, OTTIMIZZAZIONI IN CORSO**
    *   ✅ **RAG (Base):** Utilizzato ChromaDB per la vettorizzazione dei pagamenti (`src/index_pagamenti_chroma.py`) e implementata funzione base di interrogazione semantica (`src/rag_query.py`) con Google Gemini. Corretti bug relativi al parsing degli importi. **Modificato prompt per permettere uso conoscenza generale LLM come fallback.**
    *   ✅ **Intent Recognition (Base):** Implementata logica basata su **regex migliorate** in `app.py` per distinguere tra query RAG e query SQL aggregate (spesa totale per beneficiario/anno, top N fornitori/anno, **conteggio pagamenti per beneficiario/anno**).
    *   ✅ **SQL Tools:** Create funzioni Python in `src/tools/sql_aggregator_tool.py` che eseguono query SQL aggregate sul database SQLite (totale spesa per beneficiario/anno, top N fornitori/anno, **conteggio pagamenti per beneficiario/anno**). Implementata lookup del nome beneficiario normalizzato.
    *   ✅ **Fallback RAG:** Implementato meccanismo per cui se una query SQL non produce risultati (es. beneficiario non trovato), il sistema tenta automaticamente una ricerca RAG sulla domanda originale.
    *   🚧 **Arricchimento Dati Beneficiari (In Corso):**
        *   ✅ Creato script per estrarre beneficiari unici, normalizzare nomi e cercare riassunti su Wikipedia (`src/tools/wikipedia_enricher_tool.py`, `src/run_enrichment.py`).
        *   ✅ Salvataggio dei dati arricchiti (anche 'not_found') in CSV e tabella SQLite separata (`beneficiari_info`). Implementato caching per riesecuzioni.
        *   ✅ **INTEGRATO:** Recupero informazioni da `beneficiari_info` (riassunti Wikipedia) e inserimento nel contesto passato all'LLM durante le query RAG in `app.py`.
        *   [ ] Valutare fonti alternative/aggiuntive per l'arricchimento (ricerca web mirata? API registri imprese?).
    *   **Ottimizzazioni RAG (TODO):**
        *   [ ] Sperimentare Modelli di Embedding Alternativi (Locali) come BERT o BeaureaBERT.
        *   [ ] Arricchire Testo Indicizzato (valutare aggiunta metadati aggiuntivi per embedding, es. categorie?).
        *   [ ] Strategia Ibrida Retrieval/Filtro `where` (valutare se utile per query specifiche tipo "consulenze legali").
        *   [ ] Gestire meglio i casi di contesto RAG irrilevante (prompt engineering?).
    *   **Ottimizzazioni Intent/Tools (TODO):**
        *   [ ] Migliorare Intent Recognition (valutare classificatore LLM? Librerie NLP?).
        *   [ ] Sviluppare più 'Tools' SQL per aggregazioni comuni (medie, raggruppamenti per categoria?).
        *   [ ] Valutare Framework per Agenti/Tools (LangChain, LlamaIndex, Haystack?).
    *   **Gestione Conversazione (TODO):**
        *   [ ] Implementare memoria/stato della conversazione per gestire domande di follow-up (es. "e nel 2023?").

*   [ ] **Fase 6 (Pubblicazione e Accessibilità - Opzionale):**
    *   [ ] Valutare deployment applicazione Flask (considerando dimensione ChromaDB). Opzioni: PaaS con storage persistente? Ottimizzazione indice? Separazione servizi?
    *   [ ] Valutare deployment alternativo/aggiuntivo del solo database SQLite con **Datasette** per esplorazione/API dati grezzi (deployment più semplice).
    *   [ ] Esplorare possibilità di contribuire il dataset a portali Open Data esistenti.
    *   [ ] **Finalizzare Flask-Admin:** Risolvere problemi di traduzione (BabelEx vs Flask 3) o accettare UI in inglese. Nascondere/personalizzare vista "Home".

*   **Fase 7 (Miglioramenti Avanzati - TODO):**
    *   [ ] Implementare gestione contesto/memoria conversazione.
    *   [ ] Implementare fallback interattivo / disambiguazione.
    *   [ ] Ottimizzazioni RAG avanzate.

## Come usare

1.  **Clona o Scarica il Progetto:**
    *   Se usi Git: `git clone https://github.com/tuo-utente/osservatorio-statistico-busto-arsizio.git` (sostituisci con l'URL reale)
    *   Altrimenti: Scarica lo ZIP da GitHub e estrai la cartella.
2.  **Crea l'Ambiente Virtuale (Consigliato):**
    ```bash
    python -m venv .venv
    # Windows
    .\.venv\Scripts\activate
    # MacOS/Linux
    source .venv/bin/activate
    ```
3.  **Installa le Dipendenze:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configura le Variabili d'Ambiente:**
    *   Copia `.env.example` in `.env`.
    *   Apri `.env` e inserisci la tua `GOOGLE_API_KEY` ottenuta da [Google AI Studio](https://aistudio.google.com/app/apikey).
    *   Verifica/modifica gli altri percorsi se necessario (di solito i default vanno bene).
5.  **Esegui la Pipeline Dati:**
    *   **Scraping:** `python src/scraper.py` (scarica i file Excel/ODS originali)
    *   **ETL:** `python src/etl_processor.py` (crea `processed_pagamenti.csv`)
    *   **Verifica ETL (Opzionale):** `python src/verify_etl.py`
    *   **Caricamento DB:** `python src/load_to_sqlite.py` (popola `busto_pagamenti.db`)
    *   **Arricchimento Beneficiari (Opzionale ma Utile):** `python src/run_enrichment.py` (popola `beneficiari_info` nel DB, può richiedere tempo)
    *   **Indicizzazione ChromaDB:** `python src/index_pagamenti_chroma.py` (crea l'indice vettoriale, **richiede tempo!**)
6.  **Avvia l'Applicazione Web:**
    ```bash
    # Dalla root del progetto
    python -m src.app
    ```
    *   Apri il browser all'indirizzo indicato (solitamente `http://127.0.0.1:5000`).

## Come Incorporare la Chat (Widget)

Per aggiungere la chat come widget flottante sul tuo sito web:

1.  Assicurati che l'applicazione backend dell'Osservatorio sia in esecuzione e accessibile pubblicamente all'URL `[URL_DELLA_TUA_APP_DEPLOYATA]`. (Sostituisci questo placeholder con l'URL reale dopo il deployment, es. `https://osservatorio-busto.onrender.com`).
2.  Includi il seguente tag `<script>` nel codice HTML delle pagine del tuo sito dove vuoi che appaia il bottone della chat, preferibilmente subito prima della chiusura del tag `</body>`:

    ```html
    <script src="[URL_DELLA_TUA_APP_DEPLOYATA]/embed.js" defer></script>
    ```

3.  Il bottone flottante della chat apparirà automaticamente nell'angolo in basso a destra. Cliccandolo si aprirà/chiuderà la finestra della chat.

**Nota per lo sviluppatore dell'Osservatorio:** Ricorda di configurare correttamente le origini consentite (CORS) nel file `src/app.py` per includere i domini dei siti che ospiteranno il widget, sostituendo `"*"` con la lista dei domini autorizzati in produzione.

# Osservatorio Statistico Busto Arsizio - diario di sviluppo Sviluppo (Scraping)

Sto lavorando a un progetto per rendere più facili da consultare i dati del nostro Comune, in particolare quelli sulle spese (i "pagamenti"). L'idea è raccogliere i documenti ufficiali (file excel), estrarre i numeri per presentarli in due modi: cruscotto dati E interrogazione, stile ChatGPT, cosa che si può estendere a tutta la documentazione prodotta dal comune, volendo.

## L'Obiettivo Iniziale (Scraping)

Volevo creare un sistema automatico (un "programmino") che andasse sul sito della [Trasparenza del Comune](https://bustoarsizio.trasparenza-valutazione-merito.it/) e scaricasse da solo i file (tipo Excel) con l'elenco dei [pagamenti](https://bustoarsizio.trasparenza-valutazione-merito.it/web/trasparenza/dettaglio-trasparenza?p_p_id=jcitygovmenutrasversaleleftcolumn_WAR_jcitygovalbiportlet&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&p_p_col_id=column-2&p_p_col_count=1&_jcitygovmenutrasversaleleftcolumn_WAR_jcitygovalbiportlet_current-page-parent=35125&_jcitygovmenutrasversaleleftcolumn_WAR_jcitygovalbiportlet_current-page=35127) fatti ogni tre mesi o ogni anno. Questi file si trovano in realtà nell'Albo Pretorio, mostrato *dentro* una cornice (iframe) nella pagina dei pagamenti.

## Le Difficoltà Incontrate (tante, TROPPE!)

Pensavo fosse un lavoro da poche ore, ma il portale del Comune, costruito con Liferay, ha ostacolato. Dopo innumerevoli tentativi falliti (sfogliare pagine che tornavano indietro, ricerche che non trovavano nulla, pagine che apparivano diverse al programma rispetto al mio browser), siamo (io +IA) giunti alla soluzione finale. Ecco i passaggi chiave della strategia vincente, che ha richiesto l'uso di uno strumento (Selenium) per pilotare un browser Firefox:

1.  **Andare alla Pagina Principale:** Il programma apre la homepage del portale trasparenza.
2.  **Cliccare il Menu Giusto:** Imita il click sul menu principale "Amministrazione Trasparente" (usando un piccolo trucco tecnico - click via JavaScript - per aggirare un elemento che bloccava il click normale).
3.  **Cliccare il Sottomenu:** Simula il click sulla voce specifica "Dati sui pagamenti" che appare nel riquadro rosso.
4.  **Entrare nella "Cornice" (Iframe):** Il sito carica l'elenco degli atti dentro una specie di "finestra nella finestra" (un iframe). Il programma deve dire esplicitamente a Selenium: "Ok, ora guarda dentro questa cornice".
5.  **Sfogliare le Pagine (Dentro la Cornice):** A questo punto, finalmente, appare la tabella corretta! Il programma sfoglia le pagine (erano 2) cliccando su "Avanti".
6.  **Identificare i File "Pagamenti":** Per ogni pagina, il programma legge la tabella e seleziona solo le righe che contengono la parola "PAGAMENTI" nell'oggetto.
7.  **Raccogliere i Link:** Salva i link alle pagine di dettaglio per tutti gli atti identificati (34 in totale).
8.  **Scaricare (Finalmente!):** Dopo aver chiuso il browser pilotato, un sistema più semplice (`requests`) visita i link raccolti e scarica gli allegati, prendendo **solo** i file in formato Excel/ODS/XLS e ignorando i PDF (che erano 3).

**Risultato:** **VITTORIA!** Lo script (`scraper.py`) ora scarica correttamente i 31 file desiderati.

> Ma Gabbriè ma non potevi scaricarli a mano? Chi te l'ha fatto fà?!

Benvenuto nell'allucinazione informatica del "provo ad automatizzare questa cosa mettendoci **più di 20 ore** per risparmiarne forse 2 ore in un anno" 😂. Ma la soddisfazione di avercela fatta non ha prezzo (e ora abbiamo un sistema che *può* essere riutilizzato! Anche se ne mentre il sito può cambiare...).

## Prossimi Passi (Fase 2: Lavorare sui Dati)

Ora che abbiamo i file Excel/XLS, il prossimo lavoro è:

1.  **Unire e Pulire:** Scrivere codice (`pandas`) per leggere tutti i 31 file, metterli insieme in un'unica tabella e sistemare i dati (date, importi, ecc.).
2.  **Salvare nel Database:** Creare un piccolo database locale (SQLite) per conservare tutti i dati puliti.
3.  **Creare il Cruscotto Dati:** Realizzare l'interfaccia web con grafici e tabelle per esplorare le spese.
4.  **(Opzionale) Intelligenza Artificiale:** Valutare se aggiungere la funzione di interrogazione in linguaggio naturale (ChromaDB) tramite Streamlit o altra UI.
5.  **Aggiungere nel prompt ripiego cruscotto:** https://lookerstudio.google.com/u/0/reporting/13b653b0-06e4-44fa-9d33-b4f05a13ecef/page/hRYIF/edit.
6. **Aggiungere aziende partecipate, https://bustoarsizio.trasparenza-valutazione-merito.it/web/trasparenza/dettaglio-trasparenza?p_p_id=jcitygovmenutrasversaleleftcolumn_WAR_jcitygovalbiportlet&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&p_p_col_id=column-2&p_p_col_count=1&_jcitygovmenutrasversaleleftcolumn_WAR_jcitygovalbiportlet_current-page-parent=35166&_jcitygovmenutrasversaleleftcolumn_WAR_jcitygovalbiportlet_current-page=35169, utile per metadati**

## Osservazioni Finali

Questa esperienza dimostra come, nonostante i dati siano tecnicamente "pubblici", l'architettura di alcuni siti web della PA possa rendere estremamente complesso l'accesso automatico e il riuso dei dati stessi. Un plauso all'open source (Liferay), ma un monito sulla necessità di progettare tenendo conto anche dell'accessibilità programmatica per una trasparenza davvero *efficace*.

## Diario di sviluppo post recupero automatici dati

Una volta che i dati sono stati raccolti, puliti e memorizzati (Fasi 1-3), e potenzialmente visualizzati tramite un cruscotto (Fase 4), un passo successivo importante potrebbe essere rendere questi dati pubblicamente accessibili in modo standardizzato, seguendo i principi degli Open Data. Questo va oltre la semplice visualizzazione e permette ad altri cittadini, giornalisti, revisori o sviluppatori di riutilizzare facilmente i dati.

Sono state valutate diverse opzioni per raggiungere questo obiettivo, tenendo conto della necessità di soluzioni a **costo virtualmente zero** o molto basso, adatte a un progetto civico di piccola scala:

**1. Piattaforme Open Data Commerciali (Es. Socrata):**

*   **Descrizione:** Piattaforme potenti e complete come Socrata (usata da alcuni enti pubblici anche in Italia, es. Comune di Padova) offrono hosting, API automatiche, visualizzazioni e gestione dei metadati.
*   **Pro:** Soluzione "chiavi in mano", standard elevati, infrastruttura robusta.
*   **Contro:** **Costi di licenza significativi** (migliaia/decine di migliaia di euro/anno), rendendola impraticabile per progetti personali o senza budget dedicati. L'unica via sarebbe collaborare con un ente che già possiede una licenza.

**2. Piattaforme Open Data Open Source (Es. CKAN, DKAN):**

*   **Descrizione:** CKAN è lo standard de facto open source (usato da dati.gov.it e molte regioni/comuni italiani), DKAN è un'alternativa basata su Drupal. Il software è gratuito.
*   **Pro:** Standard ampiamente adottati, ricchezza di funzionalità, grande community (soprattutto CKAN).
*   **Contro:** Richiedono **hosting dedicato (VPS)** con costi associati (anche se bassi, non sono zero) e **competenze tecniche sistemistiche significative** per installazione, configurazione e manutenzione continua (aggiornamenti, sicurezza, backup). Il "costo nascosto" del tempo e delle competenze è elevato.

**3. API Custom (Es. Flask/FastAPI) + Frontend Statico:**

*   **Descrizione:** Sviluppare un'API backend dedicata (es. con Flask) che legge i dati dal database SQLite (o altro) e la deploya su una piattaforma PaaS con un piano gratuito (PythonAnywhere, Render, Fly.io, Heroku limitato, Cloud Run, etc.). Creare un frontend separato (HTML/CSS/JS) che interroga l'API e ospitarlo gratuitamente su servizi come GitHub Pages, Netlify, Vercel.
*   **Pro:** Massimo controllo e personalizzazione, **costi di hosting potenzialmente nulli** sfruttando i piani gratuiti, ottima esperienza formativa.
*   **Contro:** Richiede **lavoro di sviluppo sia backend che frontend**, bisogna definire e documentare l'API, gestire la sicurezza e la (limitata) scalabilità dei piani gratuiti.

**4. Datasette:**

*   **Descrizione:** Uno strumento Python specificamente progettato per pubblicare database SQLite (e altri) come API JSON interattive e interfacce web esplorabili con minimo sforzo. Può essere deployato facilmente su piattaforme PaaS con piani gratuiti.
*   **Pro:** **Soluzione più rapida** per ottenere API e interfaccia web da SQLite, richiede pochissimo codice aggiuntivo, **costi di hosting potenzialmente nulli** (Cloud Run, Fly.io, Render), ideale per esplorazione dati e accesso programmatico semplice.
*   **Contro:** Meno personalizzazione del frontend rispetto a una soluzione custom, ma l'interfaccia standard è già molto potente ed estendibile con plugin.

**Conclusione (per questo Progetto):**

Dato il vincolo di costo zero e la focalizzazione sull'accesso ai dati dei pagamenti, le opzioni più realistiche e consigliate per una futura pubblicazione sono:

*   **Datasette:** Per la sua rapidità e facilità nel trasformare il database SQLite in una risorsa web interattiva e un'API a costo quasi nullo.
*   **API Custom (Flask/FastAPI) + Frontend Statico:** Per una maggiore personalizzazione, se si è disposti a investire più tempo nello sviluppo.

CKAN/DKAN auto-ospitati, pur essendo potenti, presentano barriere tecniche e di costo (anche minimo) che li rendono meno adatti in questa fase. Socrata è economicamente fuori portata senza una partnership istituzionale.

## Diario di Sviluppo (Fase 5: AI - RAG)

Dopo aver ottenuto i dati puliti in formato CSV e SQLite (Fasi 1-3), si è passati all'implementazione della ricerca semantica tramite un approccio RAG (Retrieval-Augmented Generation) utilizzando ChromaDB e Google Gemini.

**Implementazione Iniziale:**
*   È stato creato uno script (`src/index_pagamenti_chroma.py`) per:
    *   Leggere i dati dal CSV processato.
    *   Combinare i campi testuali rilevanti (`DescrizioneMandato`, `Beneficiario`) per creare un "documento" per ogni pagamento.
    *   **Aggiunta Successiva:** Includere l'`Anno` nel testo indicizzato per migliorare il recupero basato sul contesto temporale.
    *   Dividere il testo in chunk.
    *   Generare embedding vettoriali per ogni chunk usando `models/text-embedding-004`.
    *   Salvare chunk, embedding e metadati (Anno, Importo, Beneficiario, etc.) in una collezione ChromaDB persistente (`pagamenti_busto`).
*   È stato creato uno script (`src/rag_query.py`) per:
    *   Prendere una domanda utente.
    *   Generare l'embedding della domanda.
    *   Interrogare ChromaDB per recuperare i chunk semanticamente più simili (`n_results`).
    *   Costruire un prompt per l'LLM Gemini (`gemini-1.5-pro-*`) contenente la domanda e il contesto recuperato.
    *   Ottenere e mostrare la risposta dell'LLM, basata solo sul contesto fornito.

**Ottimizzazione del Retrieval:**
*   **Risultati Iniziali Deludenti:** Le prime versioni mostravano risposte generiche ("Non trovo informazioni...") a causa di un recupero (retrieval) di chunk poco pertinenti, evidenziato da alte distanze nella ricerca vettoriale.
*   **Miglioramento Testo Indicizzato:** Includere l'`Anno` direttamente nel testo passato al modello di embedding ha migliorato significativamente la capacità del sistema di recuperare chunk temporalmente rilevanti.
*   **Filtro Metadati (`where`):** Si è discusso l'uso del filtro `where` di ChromaDB per forzare la ricerca solo sui documenti di un anno specifico (se menzionato nella query).
    *   **Vantaggi:** Maggiore precisione per query con vincoli temporali espliciti, contesto più pulito per l'LLM, potenziale miglioramento velocità query ChromaDB.
    *   **Compromesso:** Potenziale riduzione della flessibilità per query vaghe se l'estrazione dell'anno fallisce o è troppo rigida.
*   **Chunking:** Si è discusso l'impatto della dimensione (`DEFAULT_CHUNK_SIZE_WORDS`) e sovrapposizione (`DEFAULT_CHUNK_OVERLAP_WORDS`) dei chunk sulla qualità del retrieval. Valori diversi possono essere sperimentati per ottimizzare ulteriormente.

**Risultati Attuali:**
Il sistema RAG ora fornisce risposte specifiche e spesso accurate per molte query, recuperando contesto pertinente (con distanze migliorate) e utilizzando un LLM potente per la sintesi. Persistono aree di miglioramento, specialmente per query focalizzate su entità menzionate solo nel campo beneficiario o per richieste di aggregazione.