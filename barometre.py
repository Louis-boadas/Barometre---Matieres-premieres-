"""
Baromètre Matières Premières — Usine Nouvelle
==============================================
Script d'extraction automatique des indices de matières premières
depuis l'API Usine Nouvelle vers une base de données SQL Server.

Auteur  : Interne
Version : 1.0.0
"""

import requests
import json
import urllib3
import certifi
import pyodbc
import os
import sys
import logging

from datetime import datetime, timedelta
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration du logger
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("barometre.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chargement des variables d'environnement
# ---------------------------------------------------------------------------
load_dotenv()

SQL_SERVER   = os.environ.get("SQL_SERVER", "")
SQL_DATABASE = os.environ.get("SQL_DATABASE", "barometre")
SQL_USERNAME = os.environ.get("SQL_USERNAME", "barometre")
SQL_PASSWORD = os.environ.get("SQL_PASSWORD", "")
UN_BEARER    = os.environ.get("UN_BEARER_TOKEN", "")
UN_SESSION   = os.environ.get("UN_SESSION_COOKIE", "")

if not all([SQL_SERVER, SQL_PASSWORD, UN_BEARER, UN_SESSION]):
    logger.error(
        "Variables d'environnement manquantes. "
        "Vérifiez votre fichier .env (voir .env.example)."
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Désactivation SSL (réseau interne — à retirer si possible en production)
# ---------------------------------------------------------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
http = urllib3.PoolManager(
    cert_reqs="CERT_REQUIRED",
    ca_certs=certifi.where(),
)

# ---------------------------------------------------------------------------
# Headers & cookies d'authentification Usine Nouvelle
# ---------------------------------------------------------------------------
COOKIES = {
    "usinenouvellePROD": UN_SESSION,
}

HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Authorization": f"Bearer {UN_BEARER}",
    "Referer": "https://www.usinenouvelle.com/indices/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/109.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "IPDTrackings",
}

FLAG_REELLE = "Réelle"
FLAG_AJOUTE = "Ajouté"


# ---------------------------------------------------------------------------
# Connexion SQL Server
# ---------------------------------------------------------------------------
def get_connection():
    """Retourne une connexion pyodbc à SQL Server."""
    conn_str = (
        f"DRIVER={{SQL Server}};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={SQL_DATABASE};"
        f"UID={SQL_USERNAME};"
        f"PWD={SQL_PASSWORD}"
    )
    return pyodbc.connect(conn_str)


# ---------------------------------------------------------------------------
# Récupération des paramètres
# ---------------------------------------------------------------------------
def fetch_parametres(cursor):
    """Retourne la liste des (url, table) depuis la table `parametres`."""
    cursor.execute("SELECT URL, TBDD FROM parametres")
    rows = cursor.fetchall()
    return [(row[0], row[1]) for row in rows]


# ---------------------------------------------------------------------------
# Appel API
# ---------------------------------------------------------------------------
def fetch_indice(url: str) -> dict:
    """Appelle l'API Usine Nouvelle et retourne le JSON parsé."""
    response = requests.get(
        url,
        cookies=COOKIES,
        headers=HEADERS,
        verify=False,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Traitement d'un indice
# ---------------------------------------------------------------------------
def process_indice(cursor, cnxn, url: str, table: str) -> None:
    """
    Récupère, transforme et insère les données d'un indice
    dans la table SQL cible.
    """
    logger.info(f"Traitement : {url}")
    data = fetch_indice(url)["data"]

    code_indice   = data["code"]
    nom_indice    = data["label"]
    unite_mesure  = data["unit_label"]
    values        = data["values"]

    valeur_indices = [v["value"] for v in values]
    date_indices   = [v["date"]  for v in values]

    logger.info(f"  → {nom_indice} ({unite_mesure}) — {len(valeur_indices)} valeurs")

    # Conversion des dates ISO → datetime
    dates_dt = [
        datetime.strptime(d, "%Y-%m-%dT%H:%M:%SZ") for d in date_indices
    ]
    min_date = dates_dt[-1]
    ajd      = datetime.now()

    # --- Nettoyage de la table ---
    cursor.execute(f"DELETE FROM {table}")
    cnxn.commit()

    # --- Insertion du squelette (1 ligne par jour) ---
    current_date = min_date
    nb_jours = (ajd - min_date).days
    for _ in range(nb_jours):
        try:
            cursor.execute(
                f"INSERT INTO {table} (code_indice, name, date, unite_de_mesure, flag) "
                f"VALUES (?, ?, ?, ?, ?)",
                code_indice, nom_indice, current_date, unite_mesure, FLAG_REELLE,
            )
            cnxn.commit()
        except pyodbc.IntegrityError:
            pass
        current_date += timedelta(days=1)

    # --- Mise à jour / insertion des valeurs réelles ---
    try:
        for date_val, valeur in zip(dates_dt, valeur_indices):
            cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE date = ?", (date_val,)
            )
            count = cursor.fetchone()[0]

            if count > 0:
                cursor.execute(
                    f"UPDATE {table} SET valeur = ? WHERE date = ?",
                    (valeur, date_val),
                )
            else:
                # Pas de ligne pour cette date : on insère avec la valeur précédente
                cursor.execute(
                    f"SELECT TOP 1 valeur FROM {table} WHERE date < ? ORDER BY date DESC",
                    (date_val,),
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        f"INSERT INTO {table} (date, valeur) VALUES (?, ?)",
                        (date_val, row[0]),
                    )
                else:
                    logger.warning(f"  Aucune valeur précédente trouvée pour {date_val}")

        cnxn.commit()

        # --- Propagation des valeurs manquantes (flag "Ajouté") ---
        cursor.execute(f"SELECT date, valeur FROM {table} ORDER BY date")
        rows = cursor.fetchall()

        prev_valeur = None
        for row in rows:
            date_row, valeur_row = row
            if valeur_row is None and prev_valeur is not None:
                cursor.execute(
                    f"UPDATE {table} SET valeur = ?, flag = ? WHERE date = ?",
                    (prev_valeur, FLAG_AJOUTE, date_row),
                )
            elif valeur_row is not None:
                prev_valeur = valeur_row

        cnxn.commit()
        logger.info(f"  ✓ Table '{table}' mise à jour avec succès.")

    except Exception as exc:
        logger.error(f"  ✗ Erreur lors du traitement de '{table}' : {exc}")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
def main():
    logger.info("=== Démarrage du baromètre matières premières ===")

    cnxn   = get_connection()
    cursor = cnxn.cursor()

    parametres = fetch_parametres(cursor)
    logger.info(f"{len(parametres)} indice(s) trouvé(s) dans la table parametres.")

    for url, table in parametres:
        process_indice(cursor, cnxn, url, table)

    cursor.close()
    cnxn.close()
    logger.info("=== Traitement terminé ===")


if __name__ == "__main__":
    main()
