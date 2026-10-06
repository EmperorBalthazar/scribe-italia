# Pubblicare Scribe Italia online

La versione v1.4 è predisposta per un deploy Flask con Gunicorn e database PostgreSQL tramite `DATABASE_URL`.

Variabili d'ambiente consigliate:
- `SECRET_KEY`: stringa lunga e casuale.
- `DATABASE_URL`: fornita dal database PostgreSQL del provider.
- `BOOTSTRAP_ADMIN_NICKNAME`: nickname del primo Admin (es. admin).
- `BOOTSTRAP_ADMIN_PASSWORD`: password iniziale lunga e unica. Viene usata solo se l'Admin non esiste ancora.

Comando di avvio:
`gunicorn app:app`

Dopo il primo accesso, cambia la password dall'app tramite la voce `Password` nel menu.
