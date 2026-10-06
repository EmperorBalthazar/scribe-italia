# Scribe Italia MVP v1.6

Web app Flask per la gestione dei rapporti doganali di Regni Rinascimentali.

## Aggiornamento dalla v1.5

La v1.6 mantiene il database esistente. Non cancellare il database locale e non ricreare il PostgreSQL online.

Novità principali:
- Prefetti confinati alla propria provincia.
- Assegnazione Doganiere -> provincia -> città.
- Nuova lista "Da monitorare".
- Importazione massiva con regola: il nickname termina al primo spazio.
- Nemici/monitorati evidenziati anche tra gli Arrivati.
- Partiti non evidenziati come nemici/monitorati.
- Note automatiche distinte per Nemici e Da monitorare.

Vedi `CHANGELOG_v1_6.txt` per il dettaglio completo.

## Avvio locale

1. Esegui `INSTALLA_SCRIBE.bat`.
2. Esegui `AVVIA_SCRIBE.bat`.
3. Apri `http://127.0.0.1:5000`.

## Aggiornamento online su Render

Carica il contenuto di questa cartella nello stesso repository GitHub, sostituendo i file omonimi. Non caricare `scribe_italia.db`.
Dopo il commit, Render effettuerà normalmente il deploy automatico. La nuova tabella per le persone da monitorare viene creata automaticamente all'avvio.
