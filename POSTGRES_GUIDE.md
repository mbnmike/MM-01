# Postgres quick guide

Both apps in this repo use one local Postgres 17 server, running in Docker (via Colima) on `127.0.0.1:5432`.

| App | Database | User / password | Configured in |
| --- | --- | --- | --- |
| Express API (repo root) | `catalyst` | `catalyst` / `DB_PASSWORD` in `.env` | `.env` (`DB_*`) |
| Django site (`lot/`) | `lot` | `lot` / `lot` | `lot/.env` (`DATABASE_URL`) |

The `lot` user is the server's superuser. These passwords are for local development only. Neither `.env` file is committed; copy `.env.example` (root) or `lot/.env.example` to start one.

## Start and stop the server

```bash
colima start                  # start Docker (needed after a reboot)
cd lot && docker compose up -d   # start Postgres
docker compose ps             # is it running?
docker compose stop           # stop it; data is kept
docker compose down -v        # stop it AND delete all data (both databases)
```

Data lives in a Docker volume, so it survives `stop`, restarts and reboots. Only `down -v` erases it.

## Connect with psql

`psql` is the Postgres command-line client.

```bash
psql postgres://catalyst@127.0.0.1:5432/catalyst   # Express database (asks for DB_PASSWORD from .env)
psql postgres://lot:lot@127.0.0.1:5432/lot         # Django database
```

You'll get a prompt like `catalyst=>`. SQL statements end with `;`. Commands starting with `\` are psql shortcuts:

| Command | What it does |
| --- | --- |
| `\l` | List databases |
| `\c lot` | Switch to database `lot` |
| `\dt` | List tables |
| `\d users` | Show the columns of table `users` |
| `\du` | List users (roles) |
| `\x` | Toggle vertical output for wide rows |
| `\i file.sql` | Run a SQL file |
| `\q` | Quit |

To run one statement without opening the prompt:

```bash
psql postgres://lot:lot@127.0.0.1:5432/lot -c "SELECT count(*) FROM blog_post;"
```

## Create a table

```sql
CREATE TABLE artworks (
    id         SERIAL PRIMARY KEY,           -- auto-numbered 1, 2, 3, ...
    title      TEXT NOT NULL,
    artist     TEXT,
    year       INTEGER,
    price      NUMERIC(10, 2),               -- money: 10 digits, 2 after the point
    is_public  BOOLEAN NOT NULL DEFAULT true,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Common column types: `TEXT`, `INTEGER`, `BIGINT`, `NUMERIC(p, s)`, `BOOLEAN`, `DATE`, `TIMESTAMPTZ`, `JSONB`, `UUID`.

`CREATE TABLE IF NOT EXISTS ...` skips the step instead of erroring if the table is already there.

## Change a table

```sql
ALTER TABLE artworks ADD COLUMN medium TEXT;
ALTER TABLE artworks RENAME COLUMN medium TO material;
ALTER TABLE artworks DROP COLUMN material;
ALTER TABLE artworks RENAME TO pieces;
```

## Delete a table

```sql
DROP TABLE artworks;             -- deletes the table and all its rows
DROP TABLE IF EXISTS artworks;   -- no error if it doesn't exist
TRUNCATE artworks;               -- keeps the table, deletes all rows
```

There is no undo. If other tables reference it with `REFERENCES`, add `CASCADE` (`DROP TABLE artworks CASCADE;`), which also removes those links.

## Work with rows

```sql
INSERT INTO artworks (title, artist, year) VALUES ('Water Lilies', 'Monet', 1906);

SELECT * FROM artworks;
SELECT title, year FROM artworks WHERE year > 1900 ORDER BY year DESC LIMIT 10;

UPDATE artworks SET price = 1200.00 WHERE id = 1;

DELETE FROM artworks WHERE id = 1;
```

`UPDATE` and `DELETE` without a `WHERE` change every row. To try something safely, wrap it in a transaction:

```sql
BEGIN;
DELETE FROM artworks WHERE year < 1900;
SELECT count(*) FROM artworks;   -- check the result
ROLLBACK;                         -- undo (or COMMIT; to keep it)
```

## Create and delete databases and users

Connect as the superuser first: `psql postgres://lot:lot@127.0.0.1:5432/lot`.

```sql
CREATE ROLE myapp LOGIN PASSWORD 'secret';
CREATE DATABASE myapp OWNER myapp;

DROP DATABASE myapp;   -- nobody may be connected to it
DROP ROLE myapp;
```

## Express app (`catalyst` database)

The table definitions are in `database/schema.sql`. To create them and the demo login `test@example.com` / `1234`, run this once from the repo root:

```bash
npm run db:setup
```

It's safe to re-run. To add a table, add a `CREATE TABLE IF NOT EXISTS` to `database/schema.sql` and run `npm run db:setup` again. In code, query through the shared pool and always pass values as `$1, $2` parameters, never by pasting them into the SQL string:

```js
const { pool } = require("../database/config");
const { rows } = await pool.query("SELECT * FROM users WHERE email = $1", [email]);
```

## Django site (`lot` database): use migrations, not SQL

Django owns its tables. Don't create, alter or drop them by hand, or Django's migration history will no longer match the database. Instead, change the model in a `models.py` file and run:

```bash
cd lot && source .venv/bin/activate
python manage.py makemigrations   # writes a migration file for your change
python manage.py migrate          # applies it to the database
python manage.py showmigrations   # what's applied
python manage.py dbshell          # opens psql on this database
```

Reading data with `psql` or `dbshell` (`SELECT ...`) is always fine. To delete a table, remove its model and run `makemigrations` and `migrate`.

To wipe the Django database and start over:

```bash
psql postgres://lot:lot@127.0.0.1:5432/postgres -c "DROP DATABASE lot WITH (FORCE);" -c "CREATE DATABASE lot OWNER lot;"
python manage.py migrate && python manage.py seed
```

## Back up and restore

```bash
pg_dump postgres://lot:lot@127.0.0.1:5432/lot -Fc -f lot.dump                  # back up
pg_restore --clean --no-owner -d postgres://lot:lot@127.0.0.1:5432/lot lot.dump   # restore
```

## Prefer a GUI?

[TablePlus](https://tableplus.com), [Postico](https://eggerapps.at/postico2/) and [DBeaver](https://dbeaver.io) all connect with host `127.0.0.1`, port `5432`, and the user, password and database from the table at the top.
