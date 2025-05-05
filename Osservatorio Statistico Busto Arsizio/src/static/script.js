document.addEventListener('DOMContentLoaded', () => {
    const chatWindow = document.getElementById('chat-window');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');

    const suggestedQuestionsContainer = document.getElementById('suggested-questions');

    if (suggestedQuestionsContainer && userInput) {
        // Seleziona tutti i bottoni/link all'interno del contenitore
        const suggestedButtons = suggestedQuestionsContainer.querySelectorAll('.suggested-question');

        suggestedButtons.forEach(button => {
            button.addEventListener('click', () => {
                const questionText = button.textContent || button.innerText; // Prendi il testo del bottone
                userInput.value = questionText; // Metti il testo nell'input
                userInput.focus(); // Metti il focus sull'input

                // Invia subito la query
                 sendQuery(); // Decommenta questa riga se vuoi che il click invii subito la domanda

                // Nascondere i suggerimenti dopo il click
                suggestedQuestionsContainer.style.display = 'none';
            });
        });

        // Nascondere i suggerimenti quando l'utente inizia a scrivere?
        userInput.addEventListener('input', () => {
             if (userInput.value.trim() !== '') {
                 suggestedQuestionsContainer.style.display = 'none';
             } else {
                 // Potresti volerli mostrare di nuovo se l'input viene svuotato,
                 // ma potrebbe essere fastidioso. Lasciamoli nascosti per ora.
               // suggestedQuestionsContainer.style.display = 'flex'; // O 'block'
             }
         });

    } else {
        console.warn("Elementi per domande suggerite non trovati.");
    }

    // Funzione per rimuovere Markdown comune (** __ * _ `)
    // Resa leggermente più robusta
    function stripMarkdown(text) {
        if (!text) return '';
        let cleaned = String(text);
    // Rimuove **
    // Rimuove **testo** -> testo
    cleaned = cleaned.replace(/\*\*(.*?)\*\*/gs, '$1'); // Aggiunto 's' per multiline
    // Rimuove __testo__ -> testo
    cleaned = cleaned.replace(/__(.*?)__/gs, '$1'); // Aggiunto 's'
    // Rimuove *testo* -> testo (ma attento a non rimuovere *)
    cleaned = cleaned.replace(/(?<!\*)\*(?!\s)(.*?)(?<!\s)\*(?!\*)/g, '$1');
    // Rimuove _testo_ -> testo (ma attento a non rimuovere _)
    cleaned = cleaned.replace(/(?<!\_)_(?!\s)(.*?)(?<!\s)_(?!\_)/g, '$1');
     // Rimuove `codice` -> codice
    cleaned = cleaned.replace(/`(.*?)`/g, '$1');
    // Rimuove ```blocco codice``` (semplice)
    cleaned = cleaned.replace(/```([\s\S]*?)```/g, '$1'); // Rimuove blocco e contenuto

    // Rimuovi eventuali * o _ singoli rimasti all'inizio/fine di parole
    // che non facevano parte di coppie valide
    cleaned = cleaned.replace(/(?<=\s|^)[*_](?=\S)/g, ''); // Rimuove * o _ a inizio parola
    cleaned = cleaned.replace(/(?<=\S)[*_](?=\s|$)/g, ''); // Rimuove * o _ a fine parola
    return cleaned;
    }

    // Funzione per formattare numeri come valuta italiana (€)
        // Funzione per formattare numeri come valuta italiana (€) - VERSIONE MIGLIORATA
 function formatCurrency(value) {
        if (value === null || value === undefined) return 'N/A';
        let stringValue = String(value).trim();
        if (stringValue === '') return 'N/A';

        stringValue = stringValue.replace(/€/g, '').replace(/\s+/g, ' ').trim();

        const lastCommaIndex = stringValue.lastIndexOf(',');
        const lastDotIndex = stringValue.lastIndexOf('.');
        let decimalSeparatorChar = '.';
        let hasDecimalSeparator = false;

        if (lastCommaIndex > -1 && lastDotIndex > -1) {
            if (lastCommaIndex > lastDotIndex) { decimalSeparatorChar = ','; hasDecimalSeparator = true; }
            else { decimalSeparatorChar = '.'; hasDecimalSeparator = true; }
        } else if (lastCommaIndex > -1) { decimalSeparatorChar = ','; hasDecimalSeparator = true; }
        else if (lastDotIndex > -1) { decimalSeparatorChar = '.'; hasDecimalSeparator = true; }

        let numberStringToParse = '';
        let foundDecimalSeparator = false;
        for (let i = 0; i < stringValue.length; i++) {
            const char = stringValue[i];
            if (char >= '0' && char <= '9') { numberStringToParse += char; }
            else if (hasDecimalSeparator && char === decimalSeparatorChar && !foundDecimalSeparator) { numberStringToParse += '.'; foundDecimalSeparator = true; }
            else if (char === '.' || char === ',') { continue; }
            else if (i === 0 && char === '-') { numberStringToParse += char; }
        }

        let numValue = NaN;
        if (numberStringToParse) { try { numValue = parseFloat(numberStringToParse); } catch (e) { numValue = NaN; } }

        if (!isNaN(numValue) && isFinite(numValue)) {
             return numValue.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
        } else {
             console.warn(`formatCurrency: Impossibile parsare '${value}' come numero. Restituzione stringa originale.`);
             return String(value); // Restituisce la stringa originale non formattata
        }
    }

    // Funzione per aggiungere un messaggio alla finestra della chat - RIFORMATTAZIONE TESTO RIMOSSA
    function addMessage(text, sender, references = null, table_data = null) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', `${sender}-message`);
    
        // 1. Pulisci Markdown DAL TESTO ORIGINALE
        const cleanedText = stripMarkdown(text); // Pulisce solo Markdown, NON HTML
    
        // 2. Inserisci il testo pulito (che PUO' contenere HTML come <a> e <br>)
        if (cleanedText && cleanedText.trim() !== '') {
             const paragraph = document.createElement('p');
             paragraph.innerHTML = cleanedText.replace(/\n/g, '<br>'); // Usa innerHTML qui per interpretare <a> e <br>
             messageDiv.appendChild(paragraph);
        }
    
        // --- Logica Tabella (invariata) ---
        if (sender === 'bot' && table_data && Array.isArray(table_data) && table_data.length > 0) {
             const table = document.createElement('table');
             const thead = document.createElement('thead');
             const tbody = document.createElement('tbody');
             const tableHeaders = Object.keys(table_data[0]); // Ottieni gli header dai dati
             const headerRow = document.createElement('tr');

             // Crea header
             tableHeaders.forEach(headerKey => { // Rinominato per chiarezza
                 const th = document.createElement('th');
                 th.textContent = headerKey; // Usa la chiave come testo dell'header
                 headerRow.appendChild(th);
             });
             thead.appendChild(headerRow);
             table.appendChild(thead);

             // Crea righe dati
             table_data.forEach(rowData => {
                 const tr = document.createElement('tr');
                  // Itera sugli header PER MANTENERE L'ORDINE DELLE COLONNE
                  tableHeaders.forEach(currentHeaderKey => {
                     const value = rowData[currentHeaderKey]; // Prendi il valore usando la chiave corrente
                     const td = document.createElement('td');

                     // Applica formatCurrency solo a colonne specifiche
                     const currencyColumns = ['importo totale', 'importo', 'importoeuro', 'spesa'];
                     // --- CORREZIONE QUI ---
                     // Usa currentHeaderKey (la chiave della colonna corrente) invece di headerText
                     if (currencyColumns.includes(currentHeaderKey.toLowerCase())) {
                         td.textContent = formatCurrency(value);
                     } else {
                          if (typeof value === 'number' && Number.isInteger(value)) {
                               td.textContent = value.toLocaleString('it-IT');
                          } else {
                               td.textContent = value !== null && value !== undefined ? String(value) : '';
                          }
                     }
                     // --- FINE CORREZIONE ---

                     tr.appendChild(td);
                 });
                 tbody.appendChild(tr);
             });
             table.appendChild(tbody);
             messageDiv.appendChild(table);
        }

        // Aggiungi i riferimenti RAG se presenti (invariato)
        if (sender === 'bot' && references && Array.isArray(references) && references.length > 0) {
              const refsContainer = document.createElement('div');
              refsContainer.classList.add('references-container');
              refsContainer.innerHTML = `<button class="references-toggle">Riferimenti Trovati (${references.length}) ▼</button><div class="references-list" style="display: none;"></div>`;
              const refsList = refsContainer.querySelector('.references-list');
             references.forEach(ref => {
                 const refItem = document.createElement('div');
                 refItem.classList.add('reference-item');
                 const cleanedPreview = stripMarkdown(ref.retrieved_doc_text_preview);
                 const importoFormatted = formatCurrency(ref.importo_float || ref.importo_str); // Usa formatCurrency corretto
                 refItem.innerHTML = `<p><strong>Anno:</strong> ${ref.anno||'N/A'}, <strong>Beneficiario:</strong> ${ref.beneficiario||'N/A'}, <strong>Importo:</strong> ${importoFormatted}${ref.distance?`, <strong>Dist:</strong> ${ref.distance.toFixed(4)}`:''}</p><p class="reference-preview">Estratto: ${cleanedPreview||'N/A'}</p>`;
                 refsList.appendChild(refItem);
             });
             messageDiv.appendChild(refsContainer);
             refsContainer.querySelector('.references-toggle').addEventListener('click', function() { const list=this.nextElementSibling; const btn=this; if(list.style.display==='none'){list.style.display='block';btn.textContent=`Riferimenti Trovati (${references.length}) ▲`;}else{list.style.display='none';btn.textContent=`Riferimenti Trovati (${references.length}) ▼`;}});
        }

        // Aggiungi il messaggio al DOM solo se ha contenuto
        const hasContent = messageDiv.innerHTML.trim() !== '';
        if (hasContent) {
            chatWindow.appendChild(messageDiv);
            chatWindow.scrollTop = chatWindow.scrollHeight;
        } else {
             console.warn("Messaggio sostanzialmente vuoto non aggiunto:", text, references, table_data);
        }
    }

    // Funzioni addStatusMessage, updateStatusMessage, removeMessage
    function addStatusMessage(text, type = 'loading') {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', type);
        messageDiv.textContent = text;
        chatWindow.appendChild(messageDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
        return messageDiv;
    }
    function updateStatusMessage(text, messageElement) {
         if (messageElement) {
            messageElement.textContent = text;
            chatWindow.scrollTop = chatWindow.scrollHeight;
         }
    }
     function removeMessage(messageElement) {
        if (messageElement && chatWindow.contains(messageElement)) {
            chatWindow.removeChild(messageElement);
        }
    }
    


    // Funzione per inviare la domanda e gestire lo stream SSE
    async function sendQuery() {
        const query = userInput.value.trim();
        if (!query) {
            return;
        }

        addMessage(query, 'user');
        userInput.value = '';
        userInput.disabled = true;
        sendButton.disabled = true;

        const loadingMessageElement = addStatusMessage("Inizio elaborazione...");
        let resultReceived = false; // Flag per tracciare se abbiamo ricevuto l'evento 'result'

        try {
            const response = await fetch('/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query })
            });

            if (!response.ok) {
                 const errorData = await response.json().catch(() => ({ error_message: `Errore HTTP ${response.status}` }));
                 const errorMessage = errorData.error_message || `Errore HTTP: ${response.status}`;
                 removeMessage(loadingMessageElement);
                 addMessage(`Errore dal server: ${errorMessage}`, 'bot', null);
                 console.error('Errore API /ask:', response.status, errorData);
                 resultReceived = true;
                 return;
            }

            const contentType = response.headers.get('content-type');

            if (contentType && contentType.includes('text/event-stream')) {
                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';

                while (true) {
                    const { value, done } = await reader.read();

                    if (done) {
                         console.log('Stream terminato (done=true).');
                        // Controlla se il flag resultReceived è stato impostato.
                        // Diamo un piccolo ritardo per permettere all'ultima UI update di renderizzarsi.
                         setTimeout(() => {
                             if (!resultReceived) {
                                 console.warn("Stream terminato MA non è stato ricevuto l'evento 'result'.");
                                 removeMessage(loadingMessageElement);
                                 addMessage("Si è verificato un problema nella comunicazione con il server (stream terminato in modo inatteso).", 'bot', null);
                             }
                         }, 50); // Breve ritardo
                         break; // Esce dal loop while
                    }

                    buffer += decoder.decode(value, { stream: true });
                    const events = buffer.split('\n\n');
                    buffer = events.pop(); // Gestisce eventi incompleti

                    for (const eventString of events) {
                        if (!eventString) continue;

                        let eventType = 'message';
                        let eventDataString = '';
                        // Assicurati di gestire correttamente righe multiple di data:
                        eventString.split('\n').forEach(line => {
                             if (line.startsWith('event: ')) {
                                 eventType = line.substring('event: '.length).trim();
                             } else if (line.startsWith('data: ')) {
                                 // Rimuovi solo il prefisso 'data: ' dalla prima riga
                                 // E aggiungi il resto della linea.
                                 // Se ci sono multiple linee 'data:', queste verranno concatenate.
                                 if (eventDataString === '') { // Prima linea data
                                     eventDataString += line.substring('data: '.length);
                                 } else { // Linee data successive
                                     eventDataString += '\n' + line.substring('data: '.length);
                                 }
                             }
                        });

                        try {
                             const eventData = JSON.parse(eventDataString);
                             console.log(`Evento ricevuto (type: ${eventType}):`, eventData);

                             if (eventType === 'status') {
                                 updateStatusMessage(eventData.status, loadingMessageElement);
                             } else if (eventType === 'result') {
                                 resultReceived = true; // Imposta il flag!
                                 removeMessage(loadingMessageElement); // Rimuovi il messaggio di caricamento

                                 if (eventData.success) {
                                     addMessage(eventData.answer, 'bot', eventData.references, eventData.table_data);
                                 } else {
                                     const errorMessage = eventData.error_message || "Errore sconosciuto durante la generazione della risposta.";
                                     addMessage(`Errore: ${errorMessage}`, 'bot', null);
                                 }
                                 // Quando riceviamo il risultato, non dobbiamo leggere oltre.
                                 // Usciamo dai loop. Il 'done=true' sarà gestito dopo l'uscita.
                                 reader.cancel(); // Tenta di annullare la lettura
                                 break; // Esce dal loop 'for' degli eventi
                             }
                        } catch (e) {
                            console.error("Errore parsing evento SSE:", e, "Stringa evento:", eventDataString);
                            // Continua a leggere lo stream anche se un evento fallisce il parsing
                        }
                    } // Fine loop for events

                    // Se siamo usciti dal loop 'for' perché abbiamo trovato un 'result'
                    if (resultReceived) {
                         break; // Esce dal loop 'while'
                    }

                } // Fine loop while

            } else if (contentType && contentType.includes('application/json')) {
                 const result = await response.json();
                 console.log("Risposta API /ask (JSON):", result);
                 removeMessage(loadingMessageElement);
                 resultReceived = true; // Cache hit o errore iniziale è un risultato gestito

                 if (result.success) {
                    addMessage(result.answer, 'bot', result.references, result.table_data);
                 } else {
                    const errorMessage = result.error_message || "Errore sconosciuto durante la generazione della risposta.";
                    addMessage(`Errore: ${errorMessage}`, 'bot', null);
                 }

            } else {
                 // Tipo di contenuto inatteso
                 const textResponse = await response.text();
                 console.error("Risposta API /ask con tipo di contenuto inatteso:", contentType, "Testo:", textResponse);
                 removeMessage(loadingMessageElement);
                 resultReceived = true;
                 addMessage(`Ricevuta risposta inattesa dal server (tipo: ${contentType}).`, 'bot', null);
            }


        } catch (error) {
            console.error('Errore nella fetch /ask o lettura stream:', error);
            // Mostra errore solo se non abbiamo già gestito un risultato/errore dall'evento 'result'
            // O se l'errore non è dovuto all'annullamento manuale (reader.cancel())
            if (!resultReceived && error.name !== 'AbortError') {
                 removeMessage(loadingMessageElement);
                 let errorMessageText = `Si è verificato un problema di rete o un errore imprevisto: ${error.message}`;
                 addMessage(errorMessageText, 'bot', null);
            } else if (error.name === 'AbortError') {
                 console.log("Fetch aborted, likely by reader.cancel()");
                 // Questo è il caso atteso dopo aver ricevuto l'evento 'result' e chiamato reader.cancel()
                 // Non facciamo nulla qui, il risultato è già stato gestito.
            }
        } finally {
            userInput.disabled = false;
            sendButton.disabled = false;
            userInput.focus();
        }
    }

    // Listener (invariati)
    // Gestione click sul bottone Invia (invariato)
    sendButton.addEventListener('click', sendQuery);

    // Gestione pressione tasti nel campo input
    userInput.addEventListener('keydown', (event) => {
        // Caso 1: CTRL+Invio o CMD+Invio per inviare
        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
            event.preventDefault(); // Evita comportamenti default
            sendQuery();        // Invia la query
        }
        // Caso 2: SOLO Invio (senza Shift, Ctrl, Alt, Meta) per inviare
        else if (event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) {
            event.preventDefault(); // IMPORTANTE: Evita nuova riga nell'input se fosse multiline, o submit form se fosse dentro un form
            sendQuery();        // Invia la query
        }
        // Nota: Shift+Invio di solito inserisce una nuova riga negli input multiline,
        // quindi lo escludiamo dal comportamento di invio.
    });

    // Opzionale: Metti il focus sull'input all'avvio della pagina (invariato)
    userInput.focus();

    const embedButton = document.getElementById('embed-button');
    const embedModal = document.getElementById('embed-code-modal');
    const embedTextarea = document.getElementById('embed-code-textarea');
    const copyEmbedButton = document.getElementById('copy-embed-code');
    const closeEmbedModalButton = document.getElementById('close-embed-modal');
    const modalOverlay = document.getElementById('modal-overlay');

    // Verifica che gli elementi esistano prima di aggiungere listener
    if (embedButton && embedModal && embedTextarea && copyEmbedButton && closeEmbedModalButton && modalOverlay) {

        console.log("Elementi modale trovati, aggiungo listener..."); // Log per debug

        // Mostra il modale quando si clicca "Incorpora Chat"
        embedButton.addEventListener('click', () => {
            console.log("Bottone 'Incorpora Chat' cliccato."); // Log per debug

            // Recupera l'URL base dalla variabile globale impostata nell'HTML
            const baseUrl = window.EMBED_BASE_URL;
            if (!baseUrl) {
                 console.error("EMBED_BASE_URL non trovato. Impossibile generare codice embed.");
                 embedTextarea.value = "Errore: URL base non configurato.";
            } else {
                 // Genera lo snippet di codice
                 const embedCode = `<script src="${baseUrl}/embed.js" defer><\/script>`; // Usa \/ per </script>
                 embedTextarea.value = embedCode; // Mostra il codice
                 console.log("Codice Embed generato:", embedCode); // Log per debug
            }

            // Mostra modale e overlay
            embedModal.style.display = 'block';
            modalOverlay.style.display = 'block';
            copyEmbedButton.textContent = 'Copia Codice'; // Resetta testo bottone copia
        });

        // Funzione per chiudere il modale
        function closeModal() {
            embedModal.style.display = 'none';
            modalOverlay.style.display = 'none';
        }

        // Chiudi il modale cliccando "Chiudi" o sull'overlay
        closeEmbedModalButton.addEventListener('click', closeModal);
        modalOverlay.addEventListener('click', closeModal);

        // Copia codice negli appunti
        copyEmbedButton.addEventListener('click', () => {
            embedTextarea.select(); // Seleziona il testo
            try {
                 // Usa la nuova API Clipboard (preferita, richiede HTTPS o localhost)
                navigator.clipboard.writeText(embedTextarea.value)
                    .then(() => {
                        copyEmbedButton.textContent = 'Copiato!';
                        console.log('Codice embed copiato negli appunti');
                        // Cambia di nuovo dopo un po'
                        setTimeout(() => { copyEmbedButton.textContent = 'Copia Codice'; }, 2000);
                    })
                    .catch(err => {
                        console.error('Errore copia automatica con navigator.clipboard:', err);
                        copyEmbedButton.textContent = 'Errore Copia';
                         // Fallback con execCommand (deprecato ma funziona su più browser/contesti)
                         try {
                             const successful = document.execCommand('copy');
                             if (successful) {
                                 copyEmbedButton.textContent = 'Copiato! (fallback)';
                                 setTimeout(() => { copyEmbedButton.textContent = 'Copia Codice'; }, 2000);
                             } else {
                                 alert('Impossibile copiare automaticamente (fallback fallito). Seleziona e copia manualmente.');
                             }
                         } catch (fallbackErr) {
                             console.error('Errore con execCommand:', fallbackErr);
                             alert('Impossibile copiare automaticamente. Seleziona e copia manualmente.');
                         }
                    });
            } catch (err) {
                 // Se navigator.clipboard non è proprio definito
                 console.error('navigator.clipboard non supportato:', err);
                  try { // Tenta comunque con execCommand
                       embedTextarea.select();
                       const successful = document.execCommand('copy');
                       if (successful) {
                           copyEmbedButton.textContent = 'Copiato! (fallback)';
                           setTimeout(() => { copyEmbedButton.textContent = 'Copia Codice'; }, 2000);
                       } else {
                           alert('Impossibile copiare automaticamente. Seleziona e copia manualmente il codice.');
                       }
                   } catch (fallbackErr) {
                       console.error('Errore con execCommand (fallback principale):', fallbackErr);
                       alert('Impossibile copiare automaticamente. Seleziona e copia manualmente il codice.');
                   }
            }
        });

    } else {
        // Logga solo se non siamo in un iframe (widget.html non avrà questi elementi)
        if (window.self === window.top) {
             console.warn("Elementi per il modale 'Incorpora' non trovati sulla pagina principale.");
        }
    }
});