# Scribe Italia — MVP

Applicazione Flask per compilare rapporti doganali di Regni Rinascimentali.

## Funzioni incluse
- registrazione e login
- ruoli Admin / Prefetto / Doganiere
- province e città
- approvazione doganieri
- autorizzazioni per città
- un solo rapporto per città/data
- quattro caselle input
- parser persone, gruppi, eserciti, avvistamenti
- generazione BBCode
- storico rapporti

## Avvio rapido (Windows)
1. Installa Python 3.12 o 3.13 da https://www.python.org/downloads/ spuntando **Add Python to PATH**.
2. Estrai questa cartella, ad esempio in `C:\ScribeItalia`.
3. Apri il Prompt dei comandi dentro la cartella.
4. Crea l'ambiente virtuale: `python -m venv .venv`
5. Attivalo: `.venv\Scripts\activate`
6. Installa le dipendenze: `pip install -r requirements.txt`
7. Crea i dati demo: `flask --app app seed`
8. Avvia il sito: `flask --app app run --debug`
9. Apri `http://127.0.0.1:5000`

### Credenziali demo
- Admin: `admin` / `admin123!`
- Prefetto: `prefetto_demo` / `demo123!`
- Doganiere: `doganiere_demo` / `demo123!`

## Test
Con ambiente virtuale attivo:
`pytest -q`

## Novità v1.4
- Importazione massiva della lista nemici con anteprima prima del salvataggio.
- Riconoscimento dei nickname duplicati nelle liste del forum.
- Le diciture "già noto come" e i vecchi alias vengono ignorati.
- I duplicati già presenti nel database non vengono reinseriti.
- Aggiunti Gunicorn, PostgreSQL driver, Procfile e versione Python per facilitare il deploy online.

## Novità v1.5
- Parser persone: il nickname termina al primo spazio (oltre che alla prima virgola).
- Movimenti rinominati in **Arrivati** e **Partiti**.
- Lista nemici: il motivo compare nel report e viene richiamato anche nelle NOTE.
- Importazione massiva nemici: i nickname analizzati possono essere corretti prima dell'importazione.
- Admin: gestione del ruolo utente (Admin Centrale / Prefetto / Doganiere) e relativa provincia.
- Doganieri: interfaccia ridotta al solo flusso di nuovo rapporto; niente storico e nessuna cancellazione.
- Doganieri: data del rapporto automatica e non modificabile.
- Copia BBCode: aggiunto fallback compatibile con browser che bloccano l'API Clipboard.
- Autorizzazioni città: checkbox riallineate e più leggibili.
