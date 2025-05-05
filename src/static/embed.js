// src/static/embed.js
(function() {
    // --- Configurazione ---
    // Cambia questo con l'URL base REALE dove la tua app Flask sarà deployata
    const FLASK_APP_URL = 'http://127.0.0.1:5000'; // PER SVILUPPO LOCALE
    // const FLASK_APP_URL = 'https://tua-app-osservatorio.onrender.com'; // ESEMPIO PRODUZIONE
    // --------------------

    const WIDGET_IFRAME_SRC = `${FLASK_APP_URL}/widget`;

    // --- Stili CSS per il widget (iniettati dinamicamente) ---
    const css = `
        #osservatorio-chat-button {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background-color: #0056b3; /* Blu Comune */
            color: white;
            border: none;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            font-size: 24px; /* Dimensione icona */
            line-height: 60px; /* Centra icona verticalmente */
            text-align: center;
            cursor: pointer;
            box-shadow: 0 4px 10px rgba(0,0,0,0.2);
            z-index: 9998; /* Appena sotto l'iframe */
            transition: transform 0.2s ease-in-out;
        }
        #osservatorio-chat-button:hover {
            transform: scale(1.1);
            background-color: #004494; /* Blu più scuro */
        }
        #osservatorio-chat-widget-container {
            position: fixed;
            bottom: 90px; /* Sopra il bottone */
            right: 20px;
            width: 370px;  /* Larghezza comune per widget chat */
            height: 550px; /* Altezza comune */
            border: 1px solid #ccc;
            border-radius: 10px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.2);
            overflow: hidden; /* Nasconde angoli iframe */
            display: none; /* Nascosto inizialmente */
            z-index: 9999;
            background-color: white; /* Sfondo mentre l'iframe carica */
        }
        #osservatorio-chat-widget-iframe {
            width: 100%;
            height: 100%;
            border: none; /* Nessun bordo per l'iframe stesso */
        }

        /* Stile per icona chat (esempio semplice con testo) */
        #osservatorio-chat-button::before {
             /* Puoi usare un'icona SVG o FontAwesome qui */
             content: '?'; /* Semplice punto interrogativo */
             font-weight: bold;
        }

         /* Stile per icona chiusura quando aperto */
         #osservatorio-chat-button.widget-open::before {
             content: '×'; /* Simbolo chiusura */
             font-size: 30px; /* Leggermente più grande */
         }

        /* Responsive (opzionale) */
        @media (max-width: 450px) {
            #osservatorio-chat-widget-container {
                width: calc(100% - 30px); /* Occupa quasi tutta la larghezza */
                height: 70%;
                bottom: 80px;
                right: 15px;
                left: 15px;
            }
            #osservatorio-chat-button {
                width: 50px;
                height: 50px;
                line-height: 50px;
                font-size: 20px;
                bottom: 15px;
                right: 15px;
            }
             #osservatorio-chat-button.widget-open::before {
                 font-size: 26px;
             }
        }
    `;

    // --- Logica Widget ---
    let widgetContainer = null;
    let iframe = null;
    let chatButton = null;
    let isWidgetOpen = false;

    function createWidgetElements() {
        console.log("embed.js: Esecuzione createWidgetElements..."); // DEBUG
        try {
            // Iniettare CSS
            const styleElement = document.createElement('style');
            styleElement.textContent = css;
            // Assicurati che document.head esista
            if (document.head) {
                document.head.appendChild(styleElement);
                console.log("embed.js: CSS Injected."); // DEBUG
            } else {
                console.error("embed.js: document.head non trovato!");
                return; // Esce se head non è pronto (improbabile con defer)
            }

            // Creare Bottone
            chatButton = document.createElement('button');
            chatButton.id = 'osservatorio-chat-button';
            // Assicurati che document.body esista
            if (document.body) {
                document.body.appendChild(chatButton);
                console.log("embed.js: Bottone creato e aggiunto."); // DEBUG
            } else {
                 console.error("embed.js: document.body non trovato!");
                 return; // Esce se body non è pronto
            }


            // Creare Contenitore Iframe (nascosto)
            widgetContainer = document.createElement('div');
            widgetContainer.id = 'osservatorio-chat-widget-container';
             if (document.body) { // Controlla di nuovo per sicurezza
                document.body.appendChild(widgetContainer);
                console.log("embed.js: Contenitore Iframe creato e aggiunto."); // DEBUG
             } else {
                  console.error("embed.js: document.body non trovato per container!");
                  return;
             }


            // Creare Iframe (ma non aggiungerlo subito al DOM, o sì?)
            // Lo aggiungiamo al container, che è già nel DOM
            iframe = document.createElement('iframe');
            iframe.id = 'osservatorio-chat-widget-iframe';
            iframe.src = WIDGET_IFRAME_SRC;
            widgetContainer.appendChild(iframe); // Aggiunge iframe al container
            console.log("embed.js: Iframe creato e aggiunto al container."); // DEBUG


            // Aggiungere Event Listener al Bottone
            if (chatButton) {
                 chatButton.addEventListener('click', toggleWidget);
                 console.log("embed.js: Event listener aggiunto al bottone."); // DEBUG
            } else {
                 console.error("embed.js: chatButton non definito per listener!");
            }

        } catch (error) {
             console.error("embed.js: Errore durante creazione elementi widget:", error); // DEBUG
        }
    }

    function toggleWidget() {
        console.log("embed.js: toggleWidget chiamato. Stato attuale:", isWidgetOpen); // DEBUG
        if (widgetContainer && chatButton) { // Controlla esistenza
            isWidgetOpen = !isWidgetOpen;
            widgetContainer.style.display = isWidgetOpen ? 'block' : 'none';
            if (isWidgetOpen) {
                 chatButton.classList.add('widget-open');
            } else {
                 chatButton.classList.remove('widget-open');
            }
            console.log("embed.js: Visibilità widget aggiornata a:", widgetContainer.style.display); // DEBUG
        } else {
            console.error("embed.js: widgetContainer o chatButton non trovati in toggleWidget.");
        }
    }

    // Inizializza il widget
    console.log("embed.js: Script caricato. Stato DOM:", document.readyState); // DEBUG
     if (document.readyState === 'loading') {
          console.log("embed.js: DOM non pronto, aggiungo listener DOMContentLoaded."); // DEBUG
          document.addEventListener('DOMContentLoaded', createWidgetElements);
     } else {
          console.log("embed.js: DOM già pronto, eseguo createWidgetElements."); // DEBUG
          createWidgetElements();
     }

})();